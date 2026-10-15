"""Persistent, conservative cost reservations and request limits.

Reservations survive failures because a failed request may still be billed.
Token prices must be configured from the selected provider before enabling live use.
"""
import os
import hashlib
import ipaddress
import secrets
import sqlite3
import time
from pathlib import Path

class LimitError(Exception):
    pass

class Ledger:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS costs (id INTEGER PRIMARY KEY, amount REAL NOT NULL, created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (ip TEXT NOT NULL, created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS debates (ip TEXT NOT NULL, created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('ip_salt',secrets.token_hex(32)))

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def request(self, ip: str):
        ip=self.ip_key(ip)
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM requests WHERE created < ?', (now - 86400,))
            total = db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
            per_ip = db.execute('SELECT COUNT(*) FROM requests WHERE ip = ? AND created > ?', (ip, now-3600)).fetchone()[0]
            if total >= int(os.getenv('MAX_RUNS_PER_DAY', '100')) or per_ip >= int(os.getenv('MAX_RUNS_PER_IP_PER_HOUR', '3')):
                raise LimitError('Live request limit reached. Please try the saved sample.')
            db.execute('INSERT INTO requests VALUES (?, ?)', (ip, now))

    def reserve(self, maximum_cost: float) -> int:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            total = db.execute('SELECT COALESCE(SUM(amount), 0) FROM costs').fetchone()[0]
            if total + maximum_cost > float(os.getenv('TOTAL_MODEL_BUDGET_USD', '2')):
                raise LimitError('The demo model budget has been reached. The saved sample is still available.')
            return db.execute('INSERT INTO costs(amount, created) VALUES (?, ?)', (maximum_cost, time.time())).lastrowid

    def settle(self, reservation: int, actual_cost: float):
        with self.connect() as db:
            # Do not silently exceed the cap if provider usage was larger than expected.
            reserved = db.execute('SELECT amount FROM costs WHERE id = ?', (reservation,)).fetchone()[0]
            if actual_cost > reserved + 1e-9:
                db.execute('UPDATE costs SET amount = ? WHERE id = ?', (actual_cost, reservation))
                db.commit()
                raise LimitError('Provider usage exceeded the configured estimate; stop and review model pricing.')
            db.execute('UPDATE costs SET amount = ? WHERE id = ?', (actual_cost, reservation))

    def total(self):
        with self.connect() as db:
            return db.execute('SELECT COALESCE(SUM(amount),0) FROM costs').fetchone()[0]

    def ip_key(self, ip):
        try:
            address=ipaddress.ip_address(ip)
            ip=str(getattr(address,'ipv4_mapped',None) or address)
        except ValueError:
            pass
        with self.connect() as db:
            salt=db.execute('SELECT value FROM settings WHERE key=?',('ip_salt',)).fetchone()[0]
        return hashlib.sha256((salt+ip).encode()).hexdigest()

    def allowance(self, ip):
        key=self.ip_key(ip);limit=int(os.getenv('MAX_DEBATES_PER_IP','5'))
        with self.connect() as db:
            used=db.execute('SELECT COUNT(*) FROM debates WHERE ip=?',(key,)).fetchone()[0]
        return {'limit':limit,'used':used,'remaining':max(0,limit-used)}

    def start_debate(self, ip):
        key=self.ip_key(ip);limit=int(os.getenv('MAX_DEBATES_PER_IP','5'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used=db.execute('SELECT COUNT(*) FROM debates WHERE ip=?',(key,)).fetchone()[0]
            if used>=limit:
                raise LimitError('This network has used its five-debate allowance. The saved sample remains available.')
            db.execute('INSERT INTO debates VALUES (?,?)',(key,time.time()))

def configured_ledger(root):
    backend=os.getenv('LEDGER_BACKEND','sqlite')
    if backend=='firestore':
        from .firestore_budget import FirestoreLedger
        return FirestoreLedger()
    if backend!='sqlite':raise ValueError('Unknown ledger backend.')
    if os.getenv('K_SERVICE'):raise RuntimeError('Cloud Run requires LEDGER_BACKEND=firestore; local SQLite would lose counters.')
    return Ledger(os.getenv('LEDGER_PATH',str(root/'work'/'usage.sqlite3')))
