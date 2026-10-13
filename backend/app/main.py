import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from .budget import Ledger, LimitError
from .engine import SYSTEM, debate
from .models import AnalyzeRequest, PrepareRequest, PerspectiveOutput
from .providers import ModelProvider, ProviderError, configuration
from .retrieval import retrieve

app = FastAPI(title='Decision Atlas', version='0.1.0')
ROOT = Path(__file__).resolve().parents[2]
ledger = Ledger(os.getenv('LEDGER_PATH', str(ROOT / 'work' / 'usage.sqlite3')))
provider = ModelProvider(ledger)
run_lock = asyncio.Semaphore(1)

@app.get('/api/status')
def status():
    return configuration()

def available(request: Request):
    if not configuration()['configured']:
        raise HTTPException(503, 'Live analysis is not connected yet. Explore the labeled sample while a model is selected.')
    try:
        # Do not trust X-Forwarded-For. Configure the ASGI proxy allowlist for hosting.
        ledger.request(request.client.host if request.client else 'unknown')
    except LimitError as e:
        raise HTTPException(429, str(e)) from e

@app.post('/api/prepare')
async def prepare(payload: PrepareRequest, request: Request):
    available(request)
    try:
        async with run_lock:
            result = await provider.generate(SYSTEM,json.dumps({'task':'Propose exactly three short, distinct, topic-specific stakeholder or analytic perspectives. If the question presupposes its conclusion, propose a neutral suggested_question. Otherwise use null. Never replace the original question.','question':payload.question}),PerspectiveOutput)
        if any(not r.strip() or len(r) > 100 for r in result.perspectives):
            raise ValueError('Invalid perspectives')
        if result.suggested_question and len(result.suggested_question) > 800:
            raise ValueError('Invalid question')
        return result
    except LimitError as e:
        raise HTTPException(429,str(e)) from e
    except (ProviderError,ValueError) as e:
        raise HTTPException(502,'Could not prepare valid perspectives. Review the provider configuration.') from e

@app.post('/api/analyze')
async def analyze(payload: AnalyzeRequest, request: Request):
    if payload.include_web:
        raise HTTPException(503,'Web retrieval is not connected in this first build. Add document text and switch off web sources to use a configured model.')
    sources = retrieve(payload.question,payload.sources)
    if not sources:
        raise HTTPException(422,'Add readable evidence documents or pasted text. The system will not invent sources.')
    available(request)
    async def events():
        async with run_lock:
            try:
                async for event in debate(payload,sources,provider):
                    if await request.is_disconnected():
                        return
                    if event['type'] == 'complete':
                        event['analysis']['model'] = os.getenv('MODEL_NAME','')
                    yield 'data: '+json.dumps(event)+'\n\n'
            except LimitError as e:
                yield 'data: '+json.dumps({'type':'error','message':str(e)})+'\n\n'
            except (ProviderError, ValueError):
                yield 'data: '+json.dumps({'type':'error','message':'The model did not complete a valid analysis. Partial arguments are available, but no completed report is claimed.'})+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

if (ROOT/'dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
