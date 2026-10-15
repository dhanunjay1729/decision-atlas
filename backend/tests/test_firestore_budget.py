"""Ledger behavior with an atomic in-memory fake; not a Firestore SDK integration test."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
import pytest
from app.budget import LimitError,configured_ledger
from app.firestore_budget import FirestoreLedger

class Snapshot:
    def __init__(self,data):self.data=data
    def to_dict(self):return deepcopy(self.data)
class Ref:
    def __init__(self,store,key):self.store=store;self.key=key
    def get(self,transaction=None):return Snapshot(self.store.get(self.key))
class Transaction:
    def __init__(self,store):self.store=store
    def set(self,ref,data,merge=False):
        self.store[ref.key]={**(self.store.get(ref.key,{}) if merge else {}),**deepcopy(data)}
    def update(self,ref,data):self.set(ref,data,True)
class Client:
    def __init__(self):self.store={};self.lock=RLock()
    def collection(self,name):return self
    def document(self,key):return Ref(self.store,key)
    def run(self,callback):
        with self.lock:
            before=deepcopy(self.store)
            try:return callback(Transaction(self.store))
            except Exception:self.store.clear();self.store.update(before);raise

def test_cloud_allowance_and_budget_survive_new_client_wrappers(monkeypatch):
    monkeypatch.setenv('MAX_DEBATES_PER_IP','5');monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','.1')
    client=Client();ledger=FirestoreLedger(client,client.run)
    key=ledger.reserve(.08)
    with pytest.raises(LimitError):ledger.reserve(.03)
    ledger.settle(key,.02)
    again=FirestoreLedger(client,client.run)
    assert again.total()==pytest.approx(.02)
    assert again.ip_key('::ffff:192.0.2.1')==ledger.ip_key('192.0.2.1')
    ledger.request('192.0.2.1')
    assert ledger.allowance('192.0.2.1')['remaining']==5
    for _ in range(5):again.start_debate('192.0.2.1')
    with pytest.raises(LimitError):ledger.start_debate('192.0.2.1')
    assert ledger.allowance('192.0.2.1')['remaining']==0
    assert '192.0.2.1' not in str(client.store)

def test_cloud_atomic_starts_and_oversized_settlement(monkeypatch):
    monkeypatch.setenv('MAX_DEBATES_PER_IP','5');monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','1')
    client=Client();a=FirestoreLedger(client,client.run);b=FirestoreLedger(client,client.run)
    def start(i):
        try:(a if i%2 else b).start_debate('192.0.2.1');return True
        except LimitError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(start,range(12)))==5
    key=a.reserve(.01)
    with pytest.raises(LimitError):b.settle(key,.02)
    assert a.total()==pytest.approx(.02)

def test_cloud_storage_failure_stops_calls():
    client=Client();ledger=FirestoreLedger(client,client.run)
    def unavailable(callback):raise RuntimeError('private connection details')
    ledger.runner=unavailable
    with pytest.raises(LimitError,match='unavailable'):ledger.reserve(.01)
    assert client.store['budget']['total']==0

def test_cloud_request_limits_are_shared(monkeypatch):
    monkeypatch.setenv('MAX_RUNS_PER_DAY','2');monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','1')
    client=Client();ledger=FirestoreLedger(client,client.run)
    ledger.request('a')
    with pytest.raises(LimitError):FirestoreLedger(client,client.run).request('a')
    ledger.request('b')
    with pytest.raises(LimitError):ledger.request('c')

def test_cloud_run_rejects_ephemeral_sqlite(monkeypatch,tmp_path):
    monkeypatch.setenv('K_SERVICE','decision-atlas');monkeypatch.setenv('LEDGER_BACKEND','sqlite')
    with pytest.raises(RuntimeError,match='lose counters'):configured_ledger(tmp_path)
