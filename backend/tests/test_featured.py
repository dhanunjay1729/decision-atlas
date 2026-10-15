"""No inference calls: consent, privacy, persistence and atomic ranking tests."""
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
import pytest
from app.budget import Ledger
from app.featured import FeaturedError,FeaturedStore,FirestoreBackend,create_store
import app.featured as featured


def analysis():
    return {'mode':'live','question':'Should universities require attendance?','perspectives':['Students','Faculty'],
            'evidence_mode':'documents','report':'A balanced report considers unresolved priorities.',
            'accounted_usd':123,'api_key':'PRIVATE_KEY','publish_token':'secret',
            'arguments':[{'agent':i%2,'round':i//2+1,'position':'Consider tradeoffs','body':'A participant position.',
                          'claim_ids':['c1'],'challenges':[],'model':'private-model'} for i in range(4)],
            'claims':[{'id':'c1','agent':0,'text':'An empirical statement.','kind':'empirical','status':'insufficient','explanation':'Not established.','source_ids':['s1'],'assessments':[{'private':'omit'}]}],
            'sources':[{'id':'s1','title':'A supplied document','kind':'document','text':'PRIVATE_SOURCE_PASSAGE','url':'file:///private.pdf'},
                       {'id':'s2','title':'Public website','kind':'web','text':'PRIVATE_WEB_PASSAGE','url':'https://example.org/evidence'}]}


class Snapshot:
    def __init__(self,value):self.value=value
    def to_dict(self):return deepcopy(self.value)
class Ref:
    def __init__(self,client,key):self.client,self.key=client,key
    def document(self,key):return Ref(self.client,self.key+'/'+key)
    def collection(self,key):return Ref(self.client,self.key+'/'+key)
    def get(self,transaction=None):
        if transaction:assert not transaction.wrote,'Firestore disallows reads after writes'
        return Snapshot(self.client.data.get(self.key))
class Transaction:
    def __init__(self,client):self.client=client;self.wrote=False
    def set(self,ref,value):self.wrote=True;self.client.data[ref.key]=deepcopy(value)
class FakeCloudLedger:
    def __init__(self,ledger):
        self.data={};self.lock=RLock();self.ledger=ledger;self.collection=Ref(self,'root');self.client=self
    def ip_key(self,ip):return self.ledger.ip_key(ip)
    def runner(self,fn):
        with self.lock:
            before=deepcopy(self.data)
            try:return fn(Transaction(self))
            except Exception:self.data=before;raise


@pytest.fixture(params=['sqlite','firestore'])
def store(request,tmp_path):
    ledger=Ledger(str(tmp_path/'ledger.sqlite3'))
    if request.param=='sqlite':return create_store(tmp_path,ledger)
    cloud=FakeCloudLedger(ledger)
    return FeaturedStore(FirestoreBackend(cloud),cloud)


def test_explicit_consent_and_server_result_required(store):
    data=analysis();token=store.save_completed(data)
    assert store.list()==[]
    for consent in (False,None,1,'true'):
        with pytest.raises(FeaturedError,match='consent'):store.publish(token,consent)
    bad=analysis();bad['mode']='sample'
    with pytest.raises(FeaturedError):store.save_completed(bad)
    with pytest.raises(FeaturedError):store.publish('forged',True)
    entry=store.publish(token,True)
    assert store.publish(token,True)['id']==entry['id']
    assert len(store.list())==1


def test_public_snapshot_excludes_private_passages_tokens_cost_and_hashes(store):
    data=analysis();token=store.save_completed(data);entry=store.publish(token,True)
    data['report']='Mutated after save'
    result=store.vote(entry['id'],'192.0.2.1')
    encoded=json.dumps([result,store.list(),store.get(entry['id'])])
    for private in ('PRIVATE_SOURCE_PASSAGE','PRIVATE_WEB_PASSAGE','PRIVATE_KEY','private-model','accounted_usd','192.0.2.1',token,'voters','file:///private.pdf'):
        assert private not in encoded
    assert result['analysis']['sources'][1]['url']=='https://example.org/evidence'
    assert result['analysis']['report']!='Mutated after save'


def test_unique_normalized_ip_likes_and_trending(store):
    first=store.publish(store.save_completed(analysis()),True)
    second=store.publish(store.save_completed(analysis()),True)
    assert store.vote(first['id'],'::ffff:192.0.2.1')['likes']==1
    assert store.vote(first['id'],'192.0.2.1')['likes']==1
    assert store.list()[0]['id']==first['id']
    assert store.get(second['id'])['likes']==0
    assert len(store.list(limit=1))==1


def test_concurrent_likes_are_atomic_and_repeat_publish_idempotent(store):
    token=store.save_completed(analysis())
    with ThreadPoolExecutor(max_workers=6) as pool:entries=list(pool.map(lambda _:store.publish(token,True),range(8)))
    assert len({e['id'] for e in entries})==1
    ident=entries[0]['id']
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda i:store.vote(ident,'192.0.2.'+str(i%4)),range(12)))
    assert store.get(ident)['likes']==4


def test_capability_expiry_and_gallery_capacity(store,monkeypatch):
    token=store.save_completed(analysis());now=featured.time.time()
    monkeypatch.setattr(featured.time,'time',lambda:now+featured.DRAFT_TTL+1)
    with pytest.raises(FeaturedError,match='expired'):store.publish(token,True)
    monkeypatch.setattr(featured,'MAX_ENTRIES',1)
    store.publish(store.save_completed(analysis()),True)
    with pytest.raises(FeaturedError,match='full'):store.publish(store.save_completed(analysis()),True)


def test_sqlite_publications_survive_new_store(tmp_path):
    ledger=Ledger(str(tmp_path/'ledger.sqlite3'));store=create_store(tmp_path,ledger)
    entry=store.publish(store.save_completed(analysis()),True)
    again=create_store(tmp_path,Ledger(ledger.path))
    assert again.get(entry['id'])['analysis']['report']==entry['analysis']['report']


def test_cloud_failure_has_no_internal_details(tmp_path):
    cloud=FakeCloudLedger(Ledger(str(tmp_path/'ledger.sqlite3')))
    store=FeaturedStore(FirestoreBackend(cloud),cloud)
    def fail(fn):raise RuntimeError('secret credentials')
    cloud.runner=fail
    with pytest.raises(FeaturedError,match='temporarily unavailable') as exc:store.list()
    assert exc.value.status_code==503


def test_owner_hide_removes_public_access_and_prevents_republication(store):
    token=store.save_completed(analysis());entry=store.publish(token,True)
    store.vote(entry['id'],'192.0.2.1')
    assert store.hide(entry['id'])=={'id':entry['id'],'hidden':True}
    assert store.hide(entry['id'])=={'id':entry['id'],'hidden':True}
    assert store.list()==[]
    for operation in (lambda:store.get(entry['id']),lambda:store.vote(entry['id'],'192.0.2.2'),lambda:store.publish(token,True)):
        with pytest.raises(FeaturedError) as exc:operation()
        assert exc.value.status_code==404
    retained=store._run(lambda tx:tx.get('entry_'+entry['id']))
    assert retained['hidden'] is True and retained['analysis']['report']==entry['analysis']['report']


def test_hidden_entries_still_count_toward_storage_cap(store,monkeypatch):
    monkeypatch.setattr(featured,'MAX_ENTRIES',1)
    entry=store.publish(store.save_completed(analysis()),True)
    store.hide(entry['id'])
    with pytest.raises(FeaturedError,match='full'):store.publish(store.save_completed(analysis()),True)
