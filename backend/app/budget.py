"""Persistent, conservative cost reservations and request limits.

Reservations survive failures because a failed request may still be billed.
Token prices must be configured from the selected provider before enabling live use.
"""
import os
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

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def request(self, ip: str):
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
            if total + maximum_cost > float(os.getenv('TOTAL_MODEL_BUDGET_USD', '3')):
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
