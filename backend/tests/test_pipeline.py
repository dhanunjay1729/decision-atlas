import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.budget import Ledger, LimitError
from app.engine import apply_verification, debate
from app.models import AnalyzeRequest, ArgumentOutput, Claim, Source, VerificationOutput, ReportOutput
from app.providers import strict_schema
from app.retrieval import retrieve

def passage():
    return Source(id='s1',title='Attendance study excerpt',text='Attendance is associated with participation. This study does not establish a causal relationship.')

def test_retrieval_selects_relevant_passage_and_preserves_page():
    irrelevant=Source(id='x',title='Unrelated',text='Gardening and soil conditions.',page=2)
    relevant=Source(id='y',title='Attendance',text='Attendance participation university learning.',page=5)
    result=retrieve('university attendance',[irrelevant,relevant],limit=1)
    assert result[0].title=='Attendance' and result[0].page==5

def test_missing_citations_cannot_be_supported():
    claims=[Claim(id='c1',agent=0,text='Attendance causes higher grades.',source_ids=[])]
    output=VerificationOutput(assessments=[{'claim_id':'c1','status':'supported','source_ids':['invented'],'explanation':'Trust me.'}])
    apply_verification(claims,[passage()],output)
    assert claims[0].status=='insufficient' and claims[0].source_ids==[]

def test_duplicate_assessments_rejected():
    c=Claim(id='c1',agent=0,text='Attendance matters.',source_ids=[])
    a={'claim_id':'c1','status':'value','source_ids':[],'explanation':'Preference.'}
    with pytest.raises(ValueError):
        apply_verification([c],[passage()],VerificationOutput(assessments=[a,a]))

def test_budget_persists_and_blocks_overspend(tmp_path,monkeypatch):
    monkeypatch.setenv('TOTAL_MODEL_BUDGET_USD','0.1')
    path=str(tmp_path/'ledger.sqlite3')
    ledger=Ledger(path)
    key=ledger.reserve(.08)
    with pytest.raises(LimitError):
        Ledger(path).reserve(.03)
    ledger.settle(key,.02)
    Ledger(path).reserve(.07)

def test_client_cannot_supply_web_sources():
    with pytest.raises(ValidationError):
        AnalyzeRequest(question='Should attendance be mandatory?',perspectives=['a','b','c'],sources=[Source(id='s1',title='Fake web',text='Claim',kind='web',url='http://127.0.0.1')])

def test_strict_schema_closes_objects():
    schema=strict_schema(ArgumentOutput.model_json_schema())
    assert schema['additionalProperties'] is False
    assert schema['$defs']['DraftClaim']['additionalProperties'] is False

class FakeProvider:
    def __init__(self): self.prompts=[]
    async def generate(self,system,prompt,schema):
        data=json.loads(prompt);self.prompts.append(data)
        if schema is ArgumentOutput:
            return schema(position='Consider participation',body='The supplied excerpt describes association, not causation.',claims=[{'text':'Attendance is associated with participation.','source_ids':['s1']}],challenges=['c1','not-a-claim'] if data['round']==2 else [])
        if schema is VerificationOutput:
            return schema(assessments=[{'claim_id':c['id'],'status':'supported','source_ids':['s1'],'explanation':'The source explicitly describes an association.'} for c in data['claims']])
        return ReportOutput(report=' '.join(['A balanced comparison needs evidence and explicit priorities.']*40))

def test_two_rounds_use_equal_snapshots_and_verified_graph_ids():
    provider=FakeProvider()
    payload=AnalyzeRequest(question='Should attendance be mandatory?',perspectives=['student','faculty','administrator'],sources=[passage()])
    async def run(): return [e async for e in debate(payload,[passage()],provider)]
    events=asyncio.run(run())
    result=events[-1]['analysis']
    assert len(result['arguments'])==6
    assert [a['round'] for a in result['arguments']]==[1,1,1,2,2,2]
    assert all(p['previous_round_arguments']==[] for p in provider.prompts[:3])
    assert all(len(p['previous_round_arguments'])==3 for p in provider.prompts[3:6])
    assert all(c['status']=='supported' for c in result['claims'])
    assert all(a['challenges']==['c1'] for a in result['arguments'][3:])

def test_unconfigured_service_never_fakes_live_results(monkeypatch):
    monkeypatch.setenv('MODEL_PROVIDER','unconfigured')
    from app.main import app
    with TestClient(app) as client:
        assert client.get('/api/status').json()['configured'] is False
        response=client.post('/api/prepare',json={'question':'Should attendance be mandatory?'})
        assert response.status_code==503
        response=client.post('/api/analyze',json={'question':'Should attendance be mandatory?','perspectives':['a','b','c'],'include_web':True})
        assert response.status_code==503

def test_report_length_gets_one_correction_without_rerunning_agents():
    class ShortReportProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.report_calls=0
        async def generate(self,system,prompt,schema):
            if schema is ReportOutput:
                self.report_calls+=1
                if self.report_calls==1:
                    return ReportOutput(report=' '.join(['An incomplete brief needs more explanation.']*10))
            return await super().generate(system,prompt,schema)
    provider=ShortReportProvider()
    payload=AnalyzeRequest(question='Should attendance be mandatory?',perspectives=['student','faculty','administrator'],sources=[passage()])
    async def run(): return [e async for e in debate(payload,[passage()],provider)]
    events=asyncio.run(run())
    assert events[-1]['type']=='complete'
    assert len([e for e in events if e['type']=='argument'])==6
    assert provider.report_calls==2

def test_streaming_api_returns_six_arguments_and_complete_analysis(monkeypatch, tmp_path):
    import app.main as main
    monkeypatch.setenv('MODEL_PROVIDER','gemini')
    monkeypatch.setenv('MODEL_NAME','gemini-3.5-flash-lite')
    monkeypatch.setenv('MODEL_PREPARE_NAME','gemini-3.5-flash-lite')
    monkeypatch.setenv('MODEL_API_KEY','fake-test-key')
    monkeypatch.setenv('MODEL_INPUT_USD_PER_MILLION','0')
    monkeypatch.setenv('MODEL_OUTPUT_USD_PER_MILLION','0')
    monkeypatch.setattr(main,'provider',FakeProvider())
    monkeypatch.setattr(main,'ledger',Ledger(str(tmp_path/'ledger.sqlite3')))
    monkeypatch.setattr(main,'run_lock',asyncio.Semaphore(1))
    with TestClient(main.app) as client:
        response=client.post('/api/analyze',json={'question':'Should attendance be mandatory?','perspectives':['student','faculty','administrator'],'sources':[passage().model_dump()],'include_web':False})
    assert response.status_code==200
    events=[json.loads(block[6:]) for block in response.text.split('\n\n') if block.startswith('data: ')]
    assert len([e for e in events if e['type']=='argument'])==6
    assert events[-1]['type']=='complete'
    assert events[-1]['analysis']['model']=='gemini-3.5-flash-lite'
    assert 'fake-test-key' not in response.text
