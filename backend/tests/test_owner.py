import asyncio
import pytest
from fastapi.testclient import TestClient
from app.budget import Ledger
from app.owner import COOKIE

@pytest.fixture
def owner_app(tmp_path,monkeypatch):
 import app.main as main
 from test_pipeline import FakeProvider
 from app.featured import create_store
 monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','test')
 monkeypatch.setenv('ATLAS_OWNER_TOKEN','a'*48);monkeypatch.delenv('K_SERVICE',raising=False)
 monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','100');monkeypatch.setenv('DAILY_MODEL_BUDGET_USD','1')
 ledger=Ledger(str(tmp_path/'usage.sqlite3'));provider=FakeProvider()
 monkeypatch.setattr(main,'ledger',ledger);monkeypatch.setattr(main,'provider',provider)
 monkeypatch.setattr(main,'featured_store',create_store(tmp_path,ledger))
 monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1))
 with TestClient(main.app) as client:yield client,ledger,provider

def test_owner_cookie_bypasses_network_starts_but_logout_restores_limit(owner_app):
 client,ledger,provider=owner_app
 for _ in range(5):ledger.start_debate('testclient')
 assert client.get('/api/allowance').json()['remaining']==0
 assert client.post('/api/owner/login',json={'token':'wrong'}).status_code==401
 response=client.post('/api/owner/login',json={'token':'a'*48})
 assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
 assert client.get('/api/allowance').json()['owner'] is True
 for _ in range(6):
  response=client.post('/api/analyze',json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']})
  assert '"type": "complete"' in response.text
 assert ledger.allowance('testclient')['used']==5
 client.post('/api/owner/logout')
 assert client.post('/api/analyze',json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']}).status_code==429

def test_owner_cannot_bypass_daily_budget_or_forge_cookie(owner_app):
 client,ledger,provider=owner_app
 client.cookies.set(COOKIE,'9999999999.forged.invalid')
 assert not client.get('/api/allowance').json()['owner']
 client.cookies.clear()
 client.post('/api/owner/login',json={'token':'a'*48})
 ledger.reserve(1)
 assert client.get('/api/allowance').json()['daily']['available'] is False
 response=client.post('/api/prepare',json={'question':'Should colleges require attendance?'})
 assert response.status_code==429
 assert not provider.prompts

def test_only_completed_server_debate_can_be_published_with_consent(owner_app):
 import json
 client,ledger,provider=owner_app
 assert client.post('/api/featured',json={'publish_token':'invented','consent':True}).status_code==400
 response=client.post('/api/analyze',json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']})
 events=[json.loads(part[6:]) for part in response.text.strip().split('\n\n')]
 result=next(event['analysis'] for event in events if event['type']=='complete')
 token=result['publish_token']
 assert client.get('/api/featured').json()==[]
 assert client.post('/api/featured',json={'publish_token':token}).status_code==400
 public=client.post('/api/featured',json={'publish_token':token,'consent':True}).json()
 assert 'publish_token' not in str(public) and 'accounted_usd' not in str(public)
 ident=public['id']
 assert len(client.get('/api/featured').json())==1
 assert client.post('/api/featured/'+ident+'/like').json()['likes']==1
 assert client.post('/api/featured/'+ident+'/like').json()['likes']==1
 assert client.post('/api/featured/'+ident+'/hide').status_code==403
 client.post('/api/owner/login',json={'token':'a'*48})
 assert client.post('/api/featured/'+ident+'/hide').status_code==200
 assert client.get('/api/featured').json()==[]
 assert client.get('/api/featured/'+ident).status_code==404
