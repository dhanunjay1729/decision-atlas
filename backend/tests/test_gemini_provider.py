import asyncio
import json
import httpx
import pytest
from app.budget import Ledger
from app.models import PerspectiveOutput, VerificationOutput
from app.providers import ModelProvider, ProviderError, configuration

@pytest.fixture
def gemini_settings(monkeypatch):
    values = {
        'MODEL_PROVIDER':'gemini', 'MODEL_NAME':'gemini-3.6-flash',
        'MODEL_PREPARE_NAME':'gemini-3.5-flash-lite', 'MODEL_API_KEY':'fake-test-key',
        'MODEL_INPUT_USD_PER_MILLION':'0', 'MODEL_OUTPUT_USD_PER_MILLION':'0',
        'GEMINI_FREE_TIER_ONLY':'true', 'GEMINI_MIN_REQUEST_INTERVAL_SECONDS':'0',
        'GEMINI_THINKING_LEVEL':'low', 'MAX_OUTPUT_TOKENS':'6000',
    }
    for key, value in values.items(): monkeypatch.setenv(key, value)

def fake_transport(monkeypatch, status, data, captured):
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append({'url':url, **kwargs})
            return httpx.Response(status, json=data)
    monkeypatch.setattr('app.providers.httpx.AsyncClient', Client)

def response(content, finish='STOP'):
    return {'candidates':[{'finishReason':finish,'content':{'parts':[
        {'thought':True,'text':'Private thinking summary must be ignored.'},
        {'text':json.dumps(content)},
    ]}}], 'usageMetadata':{'promptTokenCount':50,'candidatesTokenCount':30,'thoughtsTokenCount':10}}

def test_perspective_preparation_uses_lite_and_keeps_key_out_of_url(gemini_settings, monkeypatch, tmp_path):
    captured=[]
    fake_transport(monkeypatch,200,response({'perspectives':['student','faculty','administrator'],'suggested_question':None}),captured)
    provider=ModelProvider(Ledger(str(tmp_path/'ledger.sqlite3')))
    result=asyncio.run(provider.generate('system','question',PerspectiveOutput))
    assert len(result.perspectives)==3
    assert '/gemini-3.5-flash-lite:' in captured[0]['url']
    assert 'fake-test-key' not in captured[0]['url']
    assert captured[0]['headers']['x-goog-api-key']=='fake-test-key'
    assert captured[0]['json']['generationConfig']['maxOutputTokens']==1800

def test_verifier_uses_main_model_and_json_schema(gemini_settings, monkeypatch, tmp_path):
    captured=[]
    fake_transport(monkeypatch,200,response({'assessments':[{'claim_id':'c1','status':'insufficient','source_ids':[],'explanation':'Grades were not measured.'}]}),captured)
    result=asyncio.run(ModelProvider(Ledger(str(tmp_path/'ledger.sqlite3'))).generate('system','verify',VerificationOutput))
    assert result.assessments[0].status=='insufficient'
    assert '/gemini-3.6-flash:' in captured[0]['url']
    assert captured[0]['json']['generationConfig']['thinkingConfig']=={'thinkingLevel':'low'}

@pytest.mark.parametrize('http_status,expected_status',[(429,429),(403,503),(503,503),(404,503)])
def test_provider_failures_are_actionable_without_leaking_body(gemini_settings, monkeypatch, tmp_path, http_status, expected_status):
    captured=[]
    fake_transport(monkeypatch,http_status,{'error':{'message':'fake-test-key private provider detail'}},captured)
    with pytest.raises(ProviderError) as error:
        asyncio.run(ModelProvider(Ledger(str(tmp_path/'ledger.sqlite3'))).generate('system','question',PerspectiveOutput))
    assert error.value.status_code==expected_status
    assert 'fake-test-key' not in str(error.value)
    assert len(captured)==1  # No hidden retries or paid-model fallback.

def test_free_tier_configuration_rejects_paid_only_models(gemini_settings, monkeypatch):
    monkeypatch.setenv('MODEL_NAME','gemini-4-argon')
    assert configuration()['configured'] is False

def test_free_tier_configuration_rejects_nonzero_prices(gemini_settings, monkeypatch):
    monkeypatch.setenv('MODEL_OUTPUT_USD_PER_MILLION','1.0')
    assert configuration()['configured'] is False

def test_status_never_contains_api_key(gemini_settings):
    assert 'fake-test-key' not in json.dumps(configuration())

def test_truncated_model_output_is_not_accepted(gemini_settings, monkeypatch, tmp_path):
    captured=[]
    fake_transport(monkeypatch,200,response({'perspectives':['a','b','c'],'suggested_question':None},'MAX_TOKENS'),captured)
    with pytest.raises(ProviderError,match='output limit'):
        asyncio.run(ModelProvider(Ledger(str(tmp_path/'ledger.sqlite3'))).generate('system','question',PerspectiveOutput))
