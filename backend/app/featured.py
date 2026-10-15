"""Consent-only public gallery; capped persistent snapshots and anonymous likes.

Publish capabilities expire after 24 hours. Public snapshots never retain source
passages, provider metadata, costs or voter hashes. Generated prose may quote a
source: the consent UI must explain this before publishing.
"""
import hashlib
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

MAX_ENTRIES = 200
MAX_DRAFTS = 500
MAX_LIKES = 1000
DRAFT_TTL = 86400

class FeaturedError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise FeaturedError('Invalid debate content.')
    return value


def _strings(value, maximum, length):
    if not isinstance(value, list) or len(value) > maximum:
        raise FeaturedError('Invalid debate content.')
    return [_text(item, length) for item in value]


def sanitize(analysis):
    """Allow-list a server result, excluding raw passages and private metadata."""
    if not isinstance(analysis, dict) or analysis.get('mode') != 'live':
        raise FeaturedError('Only completed live debates can be published.')
    result = {'mode': 'live', 'question': _text(analysis.get('question'), 800),
              'report': _text(analysis.get('report'), 10000),
              'perspectives': _strings(analysis.get('perspectives'), 5, 100)}
    if len(result['perspectives']) < 2 or not result['report'].strip():
        raise FeaturedError('A completed report and participants are required.')
    mode = analysis.get('evidence_mode')
    if mode not in ('knowledge', 'documents', 'web'):
        raise FeaturedError('Invalid evidence mode.')
    result['evidence_mode'] = mode
    specifications = {
        'arguments': (10, {'agent': int, 'round': int, 'position': 120, 'body': 2000,
                           'claim_ids': (20, 100), 'challenges': (8, 100)}),
        'claims': (20, {'id': 100, 'agent': int, 'text': 500, 'status': 30,
                        'source_ids': (5, 100), 'explanation': 3000, 'kind': 20}),
        'sources': (60, {'id': 100, 'title': 250, 'kind': 20}),
    }
    for key, (maximum, fields) in specifications.items():
        values = analysis.get(key, [])
        if not isinstance(values, list) or len(values) > maximum:
            raise FeaturedError('Invalid debate content.')
        result[key] = []
        for value in values:
            if not isinstance(value, dict):raise FeaturedError('Invalid debate content.')
            clean = {}
            for name, rule in fields.items():
                if name not in value:continue
                item = value[name]
                if rule is int:
                    if type(item) is not int or not 0 <= item <= 5:
                        raise FeaturedError('Invalid participant or round.')
                    clean[name] = item
                elif isinstance(rule, tuple):clean[name] = _strings(item, *rule)
                else:clean[name] = _text(item, rule)
            if key == 'sources':
                clean['text'] = ''
                url = value.get('url')
                if value.get('kind') == 'web' and isinstance(url, str) and len(url) <= 2000:
                    try:parsed = urlsplit(url)
                    except ValueError:parsed = None
                    if parsed and parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.username:
                        clean['url'] = url
            result[key].append(clean)
    if len(result['arguments']) < 4:raise FeaturedError('Only completed debates can be published.')
    if len(json.dumps(result).encode()) > 150000:raise FeaturedError('This debate is too large to publish.')
    return result


def _key(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise FeaturedError('This publication link is invalid or has expired.')
    return hashlib.sha256(token.encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{24}', value):
        raise FeaturedError('Featured debate not found.')
    return value


def _summary(entry):
    result = {key: entry[key] for key in ('id', 'published_at')}
    result.update({key: entry['analysis'][key] for key in ('question', 'perspectives', 'evidence_mode')})
    result['question'] = result['question'][:240]
    result['perspectives'] = [role[:60] for role in result['perspectives']]
    result['likes'] = len(entry.get('voters', []))
    return result


def _scored(summary):
    result = dict(summary)
    age_hours = max(0, (time.time() - result['published_at']) / 3600)
    result['score'] = round((result['likes'] + 1) / (age_hours + 2) ** 1.5, 8)
    return result


def _public(entry):
    return {**_scored(_summary(entry)), 'analysis': entry['analysis']}


class SQLiteTransaction:
    def __init__(self, db):self.db=db
    def get(self,key):
        row=self.db.execute('SELECT payload FROM featured_objects WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) if row else {}
    def set(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO featured_objects VALUES (?,?)',(key,json.dumps(value)))


class SQLiteBackend:
    def __init__(self,path):
        self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS featured_objects (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def run(self,fn):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return fn(SQLiteTransaction(db))


class FirestoreTransaction:
    def __init__(self,tx,collection):self.tx,self.collection=tx,collection
    def get(self,key):return self.collection.document(key).get(transaction=self.tx).to_dict() or {}
    def set(self,key,value):self.tx.set(self.collection.document(key),value)


class FirestoreBackend:
    def __init__(self,ledger):
        self.ledger=ledger
        self.collection=ledger.collection.document('featured').collection('items')
    def run(self,fn):return self.ledger.runner(lambda tx:fn(FirestoreTransaction(tx,self.collection)))


class FeaturedStore:
    def __init__(self,backend,ledger):self.backend,self.ledger=backend,ledger
    def _run(self,fn):
        try:return self.backend.run(fn)
        except FeaturedError:raise
        except Exception:raise FeaturedError('Featured debates are temporarily unavailable.',503) from None

    def save_completed(self,analysis):
        analysis=sanitize(analysis);now=time.time()
        # Fixed slots cap retained private draft storage, including abandoned drafts.
        for _ in range(10):
            token=secrets.token_urlsafe(32);key=_key(token);slot='draft_'+str(int(key[:8],16)%MAX_DRAFTS)
            def write(tx):
                old=tx.get(slot)
                if old.get('expires',0)>now:return False
                tx.set(slot,{'token':key,'expires':now+DRAFT_TTL,'analysis':analysis})
                return True
            if self._run(write):return token
        raise FeaturedError('The publication queue is full. Your debate is still available privately.')

    def publish(self,token,consent=False):
        if consent is not True:raise FeaturedError('Explicit consent is required to publish this debate.')
        key=_key(token);slot='draft_'+str(int(key[:8],16)%MAX_DRAFTS)
        def write(tx):
            draft=tx.get(slot);state=tx.get('state')
            if draft.get('token')!=key or draft.get('expires',0)<=time.time():
                raise FeaturedError('This publication link is invalid or has expired.')
            if draft.get('published'):
                existing=tx.get('entry_'+draft['published'])
                if not existing or existing.get('hidden'):
                    raise FeaturedError('This featured debate has been hidden by the owner.',404)
                return existing
            entries=state.get('entries',{})
            total_count=state.get('total_count',len(entries))
            if total_count>=MAX_ENTRIES:raise FeaturedError('The featured gallery is full.')
            entry={'id':secrets.token_hex(12),'published_at':time.time(),'analysis':draft['analysis'],'voters':[]}
            entries[entry['id']]=_summary(entry);draft['published']=entry['id']
            tx.set('entry_'+entry['id'],entry);tx.set('state',{'entries':entries,'total_count':total_count+1});tx.set(slot,draft)
            return entry
        return _public(self._run(write))

    def get(self,ident):
        entry=self._run(lambda tx:tx.get('entry_'+_id(ident)))
        if not entry or entry.get('hidden'):raise FeaturedError('Featured debate not found.',404)
        return _public(entry)

    def list(self,limit=20):
        entries=self._run(lambda tx:tx.get('state')).get('entries',{})
        return sorted((_scored(e) for e in entries.values()),key=lambda e:(e['score'],e['published_at']),reverse=True)[:max(1,min(50,limit))]

    def hide(self,ident):
        """Owner-only integration: retain the snapshot privately and remove discovery."""
        ident=_id(ident)
        def write(tx):
            entry=tx.get('entry_'+ident);state=tx.get('state')
            if not entry:raise FeaturedError('Featured debate not found.',404)
            if not entry.get('hidden'):
                # Preserve the lifetime cap: hiding cannot grow retained storage.
                state['total_count']=state.get('total_count',len(state.get('entries',{})))
                state.get('entries',{}).pop(ident,None)
                entry['hidden']=True
                tx.set('entry_'+ident,entry);tx.set('state',state)
            return {'id':ident,'hidden':True}
        return self._run(write)

    def vote(self,ident,ip):
        ident=_id(ident);voter=self.ledger.ip_key(ip)
        def write(tx):
            entry=tx.get('entry_'+ident);state=tx.get('state')
            if not entry or entry.get('hidden'):raise FeaturedError('Featured debate not found.',404)
            voters=entry.get('voters',[])
            if voter not in voters and len(voters)<MAX_LIKES:
                voters.append(voter);entry['voters']=voters
                state['entries'][ident]=_summary(entry)
                tx.set('entry_'+ident,entry);tx.set('state',state)
            return entry
        return _public(self._run(write))


def create_store(root,ledger):
    if hasattr(ledger,'client') and hasattr(ledger,'runner'):
        return FeaturedStore(FirestoreBackend(ledger),ledger)
    return FeaturedStore(SQLiteBackend(Path(ledger.path).with_name('featured.sqlite3')),ledger)
