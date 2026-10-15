"""Shared daily reservations, UTC rollover, and settlement across midnight."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.budget import Ledger, LimitError
from app.firestore_budget import FirestoreLedger
from test_firestore_budget import Client

@pytest.fixture(params=['sqlite','firestore'])
def ledger(request,tmp_path,monkeypatch):
    monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','20')
    monkeypatch.setenv('DAILY_MODEL_BUDGET_USD','1')
    if request.param=='sqlite':return Ledger(str(tmp_path/'daily.sqlite3'))
    client=Client()
    return FirestoreLedger(client,client.run)

def test_daily_reservations_are_atomic(ledger):
    def reserve(_):
        try:ledger.reserve(.25);return True
        except LimitError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve,range(12)))==4
    assert ledger.total()==pytest.approx(1)
    assert ledger.daily_status()['available'] is False

def test_utc_rollover_and_original_day_settlement(ledger,monkeypatch):
    import app.budget as budget
    # 2026-10-15 23:59:59 UTC. Both modules use the shared time module.
    from datetime import datetime,timezone
    before=datetime(2026,10,15,23,59,59,tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(budget.time,'time',lambda:before)
    old=ledger.reserve(1)
    assert ledger.daily_status()=={'available':False,'resets_at':'2026-10-16T00:00:00Z'}
    monkeypatch.setattr(budget.time,'time',lambda:before+2)
    assert ledger.daily_status()=={'available':True,'resets_at':'2026-10-17T00:00:00Z'}
    today=ledger.reserve(.75)
    ledger.settle(old,.1)
    # Settling yesterday must not release today's budget.
    with pytest.raises(LimitError):ledger.reserve(.3)
    assert ledger.total()==pytest.approx(.85)
    ledger.settle(today,.25)
    ledger.reserve(.75)
    assert ledger.daily_status()['available'] is False

def test_failed_calls_keep_daily_reservation(ledger):
    ledger.reserve(1) # A failed provider request is deliberately never settled.
    with pytest.raises(LimitError):ledger.reserve(.001)
    assert ledger.daily_status()['available'] is False

def test_overestimate_charge_is_persisted_on_original_day(ledger,monkeypatch):
    import app.budget as budget
    from datetime import datetime,timezone
    before=datetime(2026,10,15,23,59,59,tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(budget.time,'time',lambda:before)
    key=ledger.reserve(.9)
    monkeypatch.setattr(budget.time,'time',lambda:before+2)
    with pytest.raises(LimitError):ledger.settle(key,1.1)
    assert ledger.total()==pytest.approx(1.1)
    assert ledger.daily_status()['available'] is True
    monkeypatch.setattr(budget.time,'time',lambda:before)
    assert ledger.daily_status()['available'] is False
