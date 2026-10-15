"""Authenticated private debate history in bounded persistent storage.

Callers must supply a server-verified authentication UID. No route may accept a
client-chosen UID. Snapshots are never linked to the public featured index.
Hidden entries retain their private content and count toward storage limits.
"""
import json
import re
import secrets
import time
from pathlib import Path
from .featured import SQLiteBackend,FirestoreTransaction,sanitize,FeaturedError

MAX_PER_USER = 100
MAX_TOTAL = 1000
MAX_SNAPSHOT_BYTES = 200000


class HistoryError(Exception):
    def __init__(self,message,status_code=400):
        super().__init__(message);self.status_code=status_code


class FirestoreHistoryBackend:
    def __init__(self,ledger):
        self.ledger=ledger
        self.collection=ledger.collection.document('history').collection('items')
    def run(self,fn):return self.ledger.runner(lambda tx:fn(FirestoreTransaction(tx,self.collection)))


def snapshot(analysis):
    # The caller supplies the server-completed result. Still reject partial or
    # malformed results and preserve only known fields rather than arbitrary keys.
    try:clean=sanitize(analysis)
    except FeaturedError as exc:raise HistoryError(str(exc)) from None
    for index,source in enumerate(analysis.get('sources',[])):
        for key in ('text','page'):
            if key in source:clean['sources'][index][key]=source[key]
    for index,claim in enumerate(analysis.get('claims',[])):
        assessments=claim.get('assessments',[])
        if not isinstance(assessments,list) or len(assessments)>4:
            raise HistoryError('Invalid claim review history.')
        clean['claims'][index]['assessments']=[{k:v for k,v in a.items() if k in ('reviewer','status','explanation','source_ids')} for a in assessments if isinstance(a,dict)]
    token=analysis.get('publish_token')
    if token is not None:
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
            raise HistoryError('Invalid private publication capability.')
        clean['publish_token']=token
    try:encoded=json.dumps(clean,allow_nan=False)
    except (TypeError,ValueError):raise HistoryError('Invalid history snapshot.') from None
    if len(encoded.encode())>MAX_SNAPSHOT_BYTES:
        raise HistoryError('This debate is too large to save. Your completed debate is still available.',413)
    return json.loads(encoded)


def _ident(ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{24}',ident):
        raise HistoryError('Saved debate not found.',404)
    return ident


def _summary(entry):
    analysis=entry['analysis']
    return {'id':entry['id'],'created_at':entry['created_at'],'question':analysis['question'][:240],
            'perspectives':[r[:60] for r in analysis['perspectives']],'evidence_mode':analysis['evidence_mode']}


def _private(entry):
    return {'id':entry['id'],'created_at':entry['created_at'],'analysis':entry['analysis']}


class HistoryStore:
    def __init__(self,backend,ledger):self.backend,self.ledger=backend,ledger
    def _run(self,fn):
        try:return self.backend.run(fn)
        except HistoryError:raise
        except Exception:raise HistoryError('Private debate history is temporarily unavailable.',503) from None

    def _user(self,uid):
        if not isinstance(uid,str) or not 1<=len(uid)<=128:
            raise HistoryError('Sign in to access private debate history.',401)
        return self.ledger.ip_key('history:'+uid)

    def save_completed(self,uid,analysis):
        owner=self._user(uid);content=snapshot(analysis)
        def write(tx):
            global_state=tx.get('state');user=tx.get('user_'+owner)
            entries=user.get('entries',{})
            count=user.get('total_count',len(entries))
            if count>=MAX_PER_USER:
                raise HistoryError('Your saved debate history is full. Your completed debate is still available.',409)
            if global_state.get('total_count',0)>=MAX_TOTAL:
                raise HistoryError('Private history storage is full. Your completed debate is still available.',409)
            ident=secrets.token_hex(12)
            entry={'id':ident,'owner':owner,'created_at':time.time(),'analysis':content}
            entries[ident]=_summary(entry)
            tx.set('snapshot_'+ident,entry)
            tx.set('user_'+owner,{'entries':entries,'total_count':count+1})
            tx.set('state',{'total_count':global_state.get('total_count',0)+1})
            return ident
        return self._run(write)

    def list(self,uid):
        owner=self._user(uid)
        state=self._run(lambda tx:tx.get('user_'+owner))
        return sorted(state.get('entries',{}).values(),key=lambda e:(e['created_at'],e['id']),reverse=True)

    def get(self,uid,ident):
        owner=self._user(uid);ident=_ident(ident)
        entry=self._run(lambda tx:tx.get('snapshot_'+ident))
        if not entry or entry.get('owner')!=owner or entry.get('hidden'):
            raise HistoryError('Saved debate not found.',404)
        return _private(entry)

    def hide(self,uid,ident):
        owner=self._user(uid);ident=_ident(ident)
        def write(tx):
            entry=tx.get('snapshot_'+ident);user=tx.get('user_'+owner)
            if not entry or entry.get('owner')!=owner:
                raise HistoryError('Saved debate not found.',404)
            if not entry.get('hidden'):
                entry['hidden']=True;user.get('entries',{}).pop(ident,None)
                tx.set('snapshot_'+ident,entry);tx.set('user_'+owner,user)
            return {'id':ident,'hidden':True}
        return self._run(write)


def create_history(root,ledger):
    if hasattr(ledger,'client') and hasattr(ledger,'runner'):
        return HistoryStore(FirestoreHistoryBackend(ledger),ledger)
    return HistoryStore(SQLiteBackend(Path(ledger.path).with_name('history.sqlite3')),ledger)
