"""Unlisted debate links, stored independently of Featured moderation and ranking."""
import time
from pathlib import Path
from .featured import SQLiteBackend, FirestoreTransaction, FeaturedError, sanitize, _id

MAX_SHARES = 500

class FirestoreSharingBackend:
    def __init__(self,ledger):
        self.ledger=ledger
        self.collection=ledger.collection.document('shares').collection('items')
    def run(self,fn):return self.ledger.runner(lambda tx:fn(FirestoreTransaction(tx,self.collection)))

class SharingStore:
    def __init__(self,backend,ledger):self.backend,self.ledger=backend,ledger
    def _run(self,fn):
        try:return self.backend.run(fn)
        except FeaturedError:raise
        except Exception:raise FeaturedError('Debate sharing is temporarily unavailable.',503) from None

    def create(self,identity,analysis,consent=False):
        if consent is not True:raise FeaturedError('Explicit consent is required to share this debate.')
        ident=self.ledger.ip_key('unlisted-share:'+identity)[:24]
        content=sanitize(analysis)
        def write(tx):
            existing=tx.get('share_'+ident);state=tx.get('state')
            if existing:return existing
            count=state.get('count',0)
            if count>=MAX_SHARES:raise FeaturedError('Shared debate storage is full.')
            entry={'id':ident,'created_at':time.time(),'analysis':content}
            tx.set('share_'+ident,entry);tx.set('state',{'count':count+1})
            return entry
        return self._run(write)

    def get(self,ident):
        if not isinstance(ident,str) or len(ident)!=24:raise FeaturedError('Shared debate not found.',404)
        try:ident=_id(ident)
        except FeaturedError:raise FeaturedError('Shared debate not found.',404) from None
        entry=self._run(lambda tx:tx.get('share_'+ident))
        if not entry:raise FeaturedError('Shared debate not found.',404)
        return entry

def create_sharing(root,ledger):
    backend=FirestoreSharingBackend(ledger) if hasattr(ledger,'client') and hasattr(ledger,'runner') else SQLiteBackend(Path(ledger.path).with_name('shares.sqlite3'))
    return SharingStore(backend,ledger)
