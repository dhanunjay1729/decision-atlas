import asyncio,json
import pytest
from fastapi.testclient import TestClient
from app.budget import Ledger

@pytest.fixture
def account_app(tmp_path,monkeypatch):
 import app.main as main
 import app.accounts as accounts
 from app.history import create_history
 from app.featured import create_store
 from test_pipeline import FakeProvider
 monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','private-ai-key')
 monkeypatch.setenv('FIREBASE_PROJECT_ID','test-project');monkeypatch.setenv('FIREBASE_WEB_API_KEY','public-auth-key')
 monkeypatch.setenv('MAX_RUNS_PER_IP_PER_HOUR','100')
 ledger=Ledger(str(tmp_path/'usage.sqlite3'));provider=FakeProvider()
 monkeypatch.setattr(main,'ledger',ledger);monkeypatch.setattr(main,'provider',provider)
 monkeypatch.setattr(main,'featured_store',create_store(tmp_path,ledger));monkeypatch.setattr(main,'history_store',create_history(tmp_path,ledger));monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1))
 def verify(token):
  if token in ['signed-user-a','signed-user-b']:return {'uid':token}
  raise ValueError('invalid JWT signature')
 monkeypatch.setattr(accounts,'verify_token',verify)
 with TestClient(main.app) as client:yield client,ledger,provider

def test_history_requires_valid_verified_identity(account_app):
 client,ledger,provider=account_app
 assert client.get('/api/history').status_code==401
 assert client.get('/api/history',headers={'Authorization':'Bearer forged-user'}).status_code==401
 assert client.get('/api/history',headers={'Authorization':'Basic signed-user-a'}).status_code==401
 config=client.get('/api/auth/config').json()
 assert config['enabled'] and config['apiKey']=='public-auth-key'
 assert 'private-ai-key' not in str(config)
 assert client.post('/api/analyze',headers={'Authorization':'Bearer forged-user'},json={'question':'Should colleges require attendance?','perspectives':['a','b']}).status_code==401
 assert provider.prompts==[]

def test_completed_signed_in_debate_saves_privately_and_cannot_cross_accounts(account_app):
 client,ledger,provider=account_app
 a={'Authorization':'Bearer signed-user-a'};b={'Authorization':'Bearer signed-user-b'}
 response=client.post('/api/analyze',headers=a,json={'question':'Should colleges require attendance?','perspectives':['Students','Faculty']})
 analysis=next(json.loads(part[6:])['analysis'] for part in response.text.strip().split('\n\n') if json.loads(part[6:])['type']=='complete')
 assert analysis['history_saved']
 ident=analysis['history_id']
 assert client.get('/api/history',headers=a).json()[0]['id']==ident
 assert client.get('/api/history',headers=b).json()==[]
 assert client.get('/api/history/'+ident,headers=b).status_code==404
 assert client.post('/api/history/'+ident+'/hide',headers=b).status_code==404
 saved=client.get('/api/history/'+ident,headers=a).json()['analysis']
 assert saved['question']==analysis['question'] and saved['publish_token']==analysis['publish_token']
 assert 'accounted_usd' not in saved
 assert client.get('/api/featured').json()==[]
 assert client.post('/api/history/'+ident+'/hide',headers=a).status_code==200
 assert client.get('/api/history',headers=a).json()==[]

def test_guest_runs_not_saved_and_storage_failure_does_not_discard_completed_debate(account_app,monkeypatch):
 import app.main as main
 from app.history import HistoryError
 client,ledger,provider=account_app
 payload={'question':'Should colleges require attendance?','perspectives':['a','b']}
 response=client.post('/api/analyze',json=payload)
 assert '"type": "complete"' in response.text
 assert client.get('/api/history',headers={'Authorization':'Bearer signed-user-a'}).json()==[]
 def failed(*args):raise HistoryError('Private history unavailable.',503)
 monkeypatch.setattr(main.history_store,'save_completed',failed)
 response=client.post('/api/analyze',headers={'Authorization':'Bearer signed-user-a'},json=payload)
 assert '"type": "complete"' in response.text and '"history_saved": false' in response.text


def test_saved_share_checks_ownership_and_consent_without_inference(account_app,monkeypatch):
 import app.main as main
 from test_featured import analysis
 client,ledger,provider=account_app
 data=analysis();data['publish_token']=main.featured_store.save_completed(data)
 ident=main.history_store.save_completed('signed-user-a',data)
 a={'Authorization':'Bearer signed-user-a'};b={'Authorization':'Bearer signed-user-b'}
 url='/api/history/'+ident+'/publish'
 assert client.post(url,json={'consent':True}).status_code==401
 assert client.post(url,headers=b,json={'consent':True}).status_code==404
 assert client.post(url,headers=a,json={}).status_code==400
 shared=client.post(url,headers=a,json={'consent':True})
 assert shared.status_code==200
 entry=shared.json()
 assert client.post(url,headers=a,json={'consent':True}).json()['id']==entry['id']
 assert client.get('/api/featured/'+entry['id']).status_code==200
 assert 'PRIVATE_SOURCE_PASSAGE' not in str(entry)
 assert client.get('/api/history/'+ident,headers=a).json()['analysis']['sources'][0]['text']=='PRIVATE_SOURCE_PASSAGE'
 assert provider.prompts==[]
