"""Offline private-history tests; no auth-provider or model calls."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.budget import Ledger
from app.history import HistoryError,HistoryStore,FirestoreHistoryBackend,create_history
import app.history as history
from test_featured import analysis as featured_analysis,FakeCloudLedger

def analysis():
    data=featured_analysis();data.pop('publish_token',None)
    return data


@pytest.fixture(params=['sqlite','firestore'])
def store(request,tmp_path):
    ledger=Ledger(str(tmp_path/'ledger.sqlite3'))
    if request.param=='sqlite':return create_history(tmp_path,ledger)
    cloud=FakeCloudLedger(ledger)
    return HistoryStore(FirestoreHistoryBackend(cloud),cloud)


def test_saved_debates_are_private_to_verified_user_and_keep_sources(store):
    data=analysis();data['publish_token']='x'*43
    ident=store.save_completed('alice-authentication-uid',data)
    entry=store.get('alice-authentication-uid',ident)
    assert entry['analysis']['sources'][0]['text']=='PRIVATE_SOURCE_PASSAGE'
    assert entry['analysis']['publish_token']=='x'*43
    assert entry['analysis']['claims'][0]['assessments']==[{}]
    assert 'accounted_usd' not in entry['analysis']
    assert 'api_key' not in entry['analysis']
    assert store.list('bob-authentication-uid')==[]
    for operation in (lambda:store.get('bob-authentication-uid',ident),lambda:store.hide('bob-authentication-uid',ident)):
        with pytest.raises(HistoryError) as exc:operation()
        assert exc.value.status_code==404
    encoded=json.dumps(store.list('alice-authentication-uid'))
    assert 'PRIVATE_SOURCE_PASSAGE' not in encoded and 'publish_token' not in encoded and 'report' not in encoded
    assert 'alice-authentication-uid' not in json.dumps(entry)
    assert 'alice-authentication-uid' not in store._user('alice-authentication-uid')


def test_hide_is_idempotent_private_and_does_not_free_retained_capacity(store,monkeypatch):
    monkeypatch.setattr(history,'MAX_PER_USER',1)
    ident=store.save_completed('alice',analysis())
    assert store.hide('alice',ident)=={'id':ident,'hidden':True}
    assert store.hide('alice',ident)=={'id':ident,'hidden':True}
    assert store.list('alice')==[]
    with pytest.raises(HistoryError) as exc:store.get('alice',ident)
    assert exc.value.status_code==404
    with pytest.raises(HistoryError,match='full'):store.save_completed('alice',analysis())
    store.save_completed('bob',analysis())


def test_global_capacity_is_atomic_and_includes_hidden_snapshots(store,monkeypatch):
    monkeypatch.setattr(history,'MAX_TOTAL',3)
    def attempt(index):
        try:return store.save_completed('user'+str(index),analysis())
        except HistoryError:return None
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(10)))
    assert len([i for i in results if i])==3
    with pytest.raises(HistoryError,match='storage is full'):store.save_completed('another',analysis())


def test_invalid_snapshot_uid_ids_and_oversized_history_are_rejected(store,monkeypatch):
    for uid in ('',None,'u'*129):
        with pytest.raises(HistoryError) as exc:store.list(uid)
        assert exc.value.status_code==401
    for ident in ('../private','x'*24,'a'*23):
        with pytest.raises(HistoryError) as exc:store.get('alice',ident)
        assert exc.value.status_code==404
    bad=analysis();bad['mode']='sample'
    with pytest.raises(HistoryError):store.save_completed('alice',bad)
    monkeypatch.setattr(history,'MAX_SNAPSHOT_BYTES',10)
    with pytest.raises(HistoryError) as exc:store.save_completed('alice',analysis())
    assert exc.value.status_code==413


def test_history_storage_does_not_publish_featured_content(store):
    store.save_completed('alice',analysis())
    # Both backends have an isolated namespace and never write the featured index.
    assert store._run(lambda tx:tx.get('state')).get('entries') is None
    assert 'publish_token' not in json.dumps(store.list('alice'))


def test_sqlite_history_survives_new_store(tmp_path):
    ledger=Ledger(str(tmp_path/'ledger.sqlite3'));store=create_history(tmp_path,ledger)
    ident=store.save_completed('alice',analysis())
    again=create_history(tmp_path,Ledger(ledger.path))
    assert again.get('alice',ident)['analysis']['sources'][0]['text']=='PRIVATE_SOURCE_PASSAGE'


def test_storage_failure_is_sanitized(tmp_path):
    cloud=FakeCloudLedger(Ledger(str(tmp_path/'ledger.sqlite3')))
    store=HistoryStore(FirestoreHistoryBackend(cloud),cloud)
    def fail(fn):raise RuntimeError('private credentials')
    cloud.runner=fail
    with pytest.raises(HistoryError) as exc:store.list('alice')
    assert exc.value.status_code==503 and 'credentials' not in str(exc.value)
