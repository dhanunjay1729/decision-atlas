import asyncio
import pytest
from fastapi.testclient import TestClient
from app.budget import Ledger


@pytest.fixture
def owner_app(tmp_path,monkeypatch):
 import app.main as main
 from test_pipeline import FakeProvider
 from app.featured import create_store
 monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','test')
 import app.accounts as accounts
 from app.history import create_history
 monkeypatch.setenv('OWNER_GOOGLE_EMAIL','pantadhanunjay@gmail.com')
 monkeypatch.setenv('FIREBASE_PROJECT_ID','test-project');monkeypatch.setenv('FIREBASE_WEB_API_KEY','public-test')
 def verify(token):
  if token!='owner':raise ValueError('invalid')
  return {'uid':'owner-uid','email':'pantadhanunjay@gmail.com','email_verified':True,'firebase':{'sign_in_provider':'google.com'}}
 monkeypatch.setattr(accounts,'verify_token',verify)
 monkeypatch.delenv('K_SERVICE',raising=False)
 monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','100');monkeypatch.setenv('DAILY_MODEL_BUDGET_USD','1')
 ledger=Ledger(str(tmp_path/'usage.sqlite3'));provider=FakeProvider()
 monkeypatch.setattr(main,'ledger',ledger);monkeypatch.setattr(main,'provider',provider)
 monkeypatch.setattr(main,'featured_store',create_store(tmp_path,ledger))
 monkeypatch.setattr(main,'history_store',create_history(tmp_path,ledger))
 monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1))
 with TestClient(main.app) as client:yield client,ledger,provider

def test_google_owner_bypasses_personal_network_starts(owner_app):
 client,ledger,provider=owner_app
 for _ in range(5):ledger.start_debate('testclient')
 assert client.get('/api/allowance').json()['remaining']==0
 assert client.get('/api/allowance',headers={'Authorization':'Bearer owner'}).json()['owner'] is True
 for _ in range(6):
  response=client.post('/api/analyze',headers={'Authorization':'Bearer owner'},json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']})
  assert '"type": "complete"' in response.text
 assert ledger.allowance('testclient')['used']==5
 assert client.post('/api/analyze',json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']}).status_code==429

def test_owner_cannot_bypass_daily_budget_or_forge_cookie(owner_app):
 client,ledger,provider=owner_app
 client.cookies.set('atlas_owner','9999999999.forged.invalid')
 assert not client.get('/api/allowance').json()['owner']
 client.cookies.clear()
 ledger.reserve(1)
 assert client.get('/api/allowance',headers={'Authorization':'Bearer owner'}).json()['daily']['available'] is False
 response=client.post('/api/prepare',headers={'Authorization':'Bearer owner'},json={'question':'Should colleges require attendance?'})
 assert response.status_code==429
 assert not provider.prompts

def test_only_completed_server_debate_can_be_published_with_consent(owner_app):
 import json
 client,ledger,provider=owner_app
 assert client.post('/api/featured',json={'publish_token':'invented','consent':True}).status_code==400
 response=client.post('/api/analyze',headers={'Authorization':'Bearer owner'},json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']})
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
 assert client.post('/api/featured/'+ident+'/hide',headers={'Authorization':'Bearer owner'}).status_code==200
 assert client.get('/api/featured').json()==[]
 assert client.get('/api/featured/'+ident).status_code==404


def test_admin_delete_requires_verified_google_and_keeps_private_history(owner_app,monkeypatch):
 import app.main as main
 import app.accounts as accounts
 from test_featured import analysis
 client,ledger,provider=owner_app
 data=analysis();data['publish_token']=main.featured_store.save_completed(data)
 ident=main.history_store.save_completed('owner-uid',data)
 public=main.featured_store.publish_saved(ident,data,True)
 url='/api/featured/'+public['id']
 assert client.delete(url).status_code==403
 assert client.delete(url,headers={'Authorization':'Bearer forged'}).status_code==403
 verified=accounts.verify_token
 def verify(token):
  if token=='password-owner':return {'uid':'owner-uid','email':'pantadhanunjay@gmail.com','email_verified':True,'firebase':{'sign_in_provider':'password'}}
  return verified(token)
 monkeypatch.setattr(accounts,'verify_token',verify)
 assert client.delete(url,headers={'Authorization':'Bearer password-owner'}).status_code==403
 for _ in range(2):assert client.delete(url,headers={'Authorization':'Bearer owner'}).status_code==200
 assert client.get(url).status_code==404 and client.get('/api/featured').json()==[]
 assert client.get('/api/history/'+ident,headers={'Authorization':'Bearer owner'}).status_code==200
 assert client.post('/api/history/'+ident+'/publish',headers={'Authorization':'Bearer owner'},json={'consent':True}).status_code==404
 assert provider.prompts==[]
