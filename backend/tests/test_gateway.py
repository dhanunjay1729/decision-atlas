import asyncio
import json
import httpx
import pytest
from app.budget import Ledger
from app.engine import apply_verification, apply_crosscheck
from app.gateway import GatewayProvider, estimate
from app.models import AnalyzeRequest, Claim, Source, VerificationOutput, PerspectiveOutput
from app.providers import ProviderError,configuration

def test_stage_routing_stays_in_the_inexpensive_pool(tmp_path):
    provider=GatewayProvider(Ledger(str(tmp_path/'usage.sqlite3')))
    request=AnalyzeRequest(question='Which option should we consider?',perspectives=['a','b','c','d','e'],include_web=True)
    assert [provider.for_stage('argument',request,i).key for i in range(5)]==['qwen','haiku','qwen','qwen','qwen']
    request.include_web=False
    assert all(provider.for_stage('argument',request,i).key=='dense' for i in range(5))
    assert provider.for_stage('crosscheck').key=='crosscheck'

def test_disagreements_do_not_receive_a_confident_label():
    source=Source(id='s1',title='Evidence',text='An observational increase; no control group.')
    claims=[Claim(id='c1',agent=0,text='This caused an increase.',source_ids=['s1'])]
    a=VerificationOutput(assessments=[dict(claim_id='c1',status='supported',source_ids=['s1'],explanation='Reported increase.')])
    b=VerificationOutput(assessments=[dict(claim_id='c1',status='insufficient',source_ids=['s1'],explanation='No causal design.')])
    apply_verification(claims,[source],a);apply_crosscheck(claims,[source],a,b)
    assert claims[0].status=='review' and len(claims[0].assessments)==2

def test_estimate_scales_with_count_and_web():
    two=AnalyzeRequest(question='Which option should we consider?',perspectives=['a','b'])
    five=AnalyzeRequest(question=two.question,perspectives=['a','b','c','d','e'])
    assert estimate(five,[])['estimated_usd']>estimate(two,[])['estimated_usd']
    two.include_web=True
    assert estimate(two,[])['search_calls']==1
    assert estimate(two,[])['estimated_usd']>=.0055

def test_gateway_pins_provider_and_reports_actual_cost(monkeypatch,tmp_path):
    monkeypatch.setenv('AI_GATEWAY_API_KEY','private-test-key')
    monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','1')
    captured=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            captured.append(kwargs)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'perspectives':['a','b'],'suggested_question':None})}}],'usage':{'cost':.0001}})
    monkeypatch.setattr('app.gateway.httpx.AsyncClient',Client)
    ledger=Ledger(str(tmp_path/'usage.sqlite3'))
    result=asyncio.run(GatewayProvider(ledger).generate('system','question',PerspectiveOutput))
    assert len(result.perspectives)==2
    payload=captured[0]['json']
    assert payload['providerOptions']['gateway']=={'only':['alibaba']}
    assert payload['reasoning']=={'enabled':False}
    assert payload['max_tokens']==600
    with ledger.connect() as db:assert db.execute('select sum(amount) from costs').fetchone()[0]==.0001

def test_shared_search_used_once_even_with_five_debaters(monkeypatch,tmp_path):
    import app.main as main
    from fastapi.testclient import TestClient
    from test_pipeline import FakeProvider
    monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','private-test-key')
    monkeypatch.setattr(main,'provider',FakeProvider());monkeypatch.setattr(main,'ledger',Ledger(str(tmp_path/'usage.sqlite3')))
    monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1));calls=[]
    async def search(question,ledger):
        calls.append(question)
        return [Source(id='web1',title='Live excerpt',text='A relevant passage.',kind='web',url='https://example.com/study')]
    monkeypatch.setattr(main,'search',search)
    with TestClient(main.app) as client:
        response=client.post('/api/analyze',json={'question':'Which option should we consider?','perspectives':['a','b','c','d','e'],'include_web':True})
    events=[json.loads(b[6:]) for b in response.text.split('\n\n') if b.startswith('data: ')]
    assert len(calls)==1
    assert events[-1]['type']=='complete'
    assert len(events[-1]['analysis']['arguments'])==10
    assert events[-1]['analysis']['sources'][0]['kind']=='web'

def test_web_evidence_is_not_crowded_out_by_documents():
    from app.main import select_sources
    sources=[Source(id=f'd{i}',title=f'Document {i}',text='Useful evidence.') for i in range(5)]
    sources.append(Source(id='w',title='Current source',text='Current evidence.',kind='web',url='https://example.com'))
    result=select_sources('current evidence',sources)
    assert any(s.kind=='web' for s in result)
    assert len({s.id for s in result})==len(result)
    assert sum(len(s.text) for s in result)<=6500

def test_gateway_status_does_not_expose_credentials(monkeypatch):
    monkeypatch.setenv('MODEL_PROVIDER','vercel');monkeypatch.setenv('AI_GATEWAY_API_KEY','private-test-key')
    assert configuration()['web_available'] is True
    assert 'private-test-key' not in json.dumps(configuration())

def test_rate_limited_dense_model_falls_back_once_and_cools_down(monkeypatch,tmp_path):
    from app.models import ArgumentOutput
    monkeypatch.setenv('AI_GATEWAY_API_KEY','private-test-key')
    monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','1')
    calls=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            calls.append(kwargs['json'])
            if len(calls)==1:return httpx.Response(429,json={'error':'private-test-key'})
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'position':'Consider both','body':'A careful argument.','claims':[{'text':'A value choice.','source_ids':[],'kind':'value'}],'challenges':[]})}}],'usage':{'cost':.0002}})
    monkeypatch.setattr('app.gateway.httpx.AsyncClient',Client)
    pool=GatewayProvider(Ledger(str(tmp_path/'usage.sqlite3')))
    request=AnalyzeRequest(question='Which option should we consider?',perspectives=['a','b'])
    draft=pool.for_stage('argument',request,0)
    asyncio.run(draft.generate('system','question',ArgumentOutput))
    assert [x['model'] for x in calls]==['alibaba/qwen3.8-27b','anthropic/claude-haiku-5.5']
    assert draft.used_fallback and draft.model=='anthropic/claude-haiku-5.5'
    assert pool.for_stage('argument',request,1).key=='haiku'
    assert calls[1]['providerOptions']['gateway']['only']==['anthropic']

def test_verification_batches_cover_twenty_claims_without_duplicates():
    from app.engine import verify_batches
    class Verifier:
        def __init__(self):self.sizes=[]
        async def generate(self,system,prompt,schema):
            claims=json.loads(prompt)['claims'];self.sizes.append(len(claims))
            return schema(assessments=[dict(claim_id=c['id'],status='insufficient',source_ids=[],explanation='Not established.') for c in claims])
    verifier=Verifier()
    result=asyncio.run(verify_batches(verifier,json.dumps({'claims':[{'id':f'c{i}'} for i in range(20)],'sources':[]})))
    assert verifier.sizes==[8,8,4]
    assert len({a.claim_id for a in result.assessments})==20
