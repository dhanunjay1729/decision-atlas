from concurrent.futures import ThreadPoolExecutor
import pytest
from app.budget import Ledger,LimitError

def test_five_starts_persist_and_suggestions_do_not_consume_them(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_DEBATES_PER_IP','5');monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','100')
    path=str(tmp_path/'usage.sqlite3');ledger=Ledger(path)
    for _ in range(3):ledger.request('192.0.2.1')
    assert ledger.allowance('192.0.2.1')['remaining']==5
    for _ in range(5):ledger.start_debate('192.0.2.1')
    assert Ledger(path).allowance('192.0.2.1')['remaining']==0
    with pytest.raises(LimitError):Ledger(path).start_debate('192.0.2.1')
    assert ledger.allowance('192.0.2.2')['remaining']==5
    with ledger.connect() as db:
        assert '192.0.2.1' not in str(db.execute('select ip from debates').fetchall())

def test_atomic_allowance_and_ip_normalization(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_DEBATES_PER_IP','5')
    ledger=Ledger(str(tmp_path/'usage.sqlite3'))
    def attempt(_):
        try:ledger.start_debate('::ffff:192.0.2.1');return True
        except LimitError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(12)))
    assert sum(results)==5
    assert ledger.allowance('192.0.2.1')['remaining']==0

def test_sixth_api_debate_is_blocked_before_model_work(tmp_path,monkeypatch):
    import asyncio,json
    import app.main as main
    from fastapi.testclient import TestClient
    from test_pipeline import FakeProvider
    monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','private-test-key')
    monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','100');monkeypatch.setenv('MAX_DEBATES_PER_IP','5')
    provider=FakeProvider();ledger=Ledger(str(tmp_path/'usage.sqlite3'))
    monkeypatch.setattr(main,'provider',provider);monkeypatch.setattr(main,'ledger',ledger)
    monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1))
    with TestClient(main.app) as client:
        payload={'question':'Should colleges require attendance?','perspectives':['a','b']}
        for _ in range(5):
            response=client.post('/api/analyze',json=payload)
            assert '"type": "complete"' in response.text
        calls=len(provider.prompts)
        assert client.get('/api/allowance').json()['remaining']==0
        assert client.post('/api/analyze',json=payload).status_code==429
        assert len(provider.prompts)==calls
