import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from .budget import Ledger, LimitError
from .engine import SYSTEM, debate
from .models import AnalyzeRequest, PrepareRequest, PerspectiveOutput
from .providers import ModelProvider, ProviderError, configuration
from .retrieval import retrieve
from .gateway import GatewayProvider, estimate
from .search import search

app = FastAPI(title='Decision Atlas', version='0.1.0')
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env', override=False)
ledger = Ledger(os.getenv('LEDGER_PATH', str(ROOT / 'work' / 'usage.sqlite3')))
provider = GatewayProvider(ledger) if os.getenv('MODEL_PROVIDER')=='vercel' else ModelProvider(ledger)
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
            preparer=provider.for_stage('prepare') if hasattr(provider,'for_stage') else provider
            result = await preparer.generate(SYSTEM,json.dumps({'task':f'Propose exactly {payload.participant_count} distinct topic-specific stakeholder or analytic perspectives. Each perspective must be a short LABEL of at most six words and 100 characters, not a description or an argument. If the question presupposes its conclusion, propose a neutral suggested_question. Otherwise use null. Never replace the original question.','question':payload.question}),PerspectiveOutput)
        if len(result.perspectives) != payload.participant_count or any(not r.strip() or len(r) > 100 for r in result.perspectives):
            raise ValueError('Invalid perspectives')
        if result.suggested_question and len(result.suggested_question) > 800:
            raise ValueError('Invalid question')
        return result
    except LimitError as e:
        raise HTTPException(429,str(e)) from e
    except ProviderError as e:
        raise HTTPException(e.status_code, str(e)) from None
    except ValueError as e:
        raise HTTPException(502,'Could not prepare valid perspectives. Review the provider configuration.') from e

@app.post('/api/analyze')
async def analyze(payload: AnalyzeRequest, request: Request):
    if payload.include_web and not configuration()['web_available']:
        raise HTTPException(503,'Web search is not configured. Turn it off or configure AI Gateway.')
    sources = select_sources(payload.question,payload.sources)
    available(request)
    async def events():
        async with run_lock:
            try:
                if await request.is_disconnected(): return
                before=ledger.total()
                selected=sources
                if payload.include_web:
                    yield 'data: '+json.dumps({'type':'progress','message':'Retrieving shared Perplexity evidence'})+'\n\n'
                    web_sources=await search(payload.question,ledger)
                    selected=select_sources(payload.question,payload.sources+web_sources)
                yield 'data: '+json.dumps({'type':'sources','sources':[s.model_dump() for s in selected]})+'\n\n'
                async for event in debate(payload,selected,provider):
                    if await request.is_disconnected():
                        return
                    if event['type'] == 'complete':
                        event['analysis']['model'] = configuration()['model']
                        event['analysis']['accounted_usd'] = round(ledger.total()-before,6)
                    yield 'data: '+json.dumps(event)+'\n\n'
            except LimitError as e:
                yield 'data: '+json.dumps({'type':'error','message':str(e)})+'\n\n'
            except ProviderError as e:
                yield 'data: '+json.dumps({'type':'error','message':str(e)})+'\n\n'
            except ValueError:
                yield 'data: '+json.dumps({'type':'error','message':'The model did not complete a valid analysis. Partial arguments are available, but no completed report is claimed.'})+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

def select_sources(question,sources):
    # Bound repeated context cost; retain representation of individual documents.
    result=[];remaining=6500
    groups={}
    for source in sources:groups.setdefault((source.title,source.kind),[]).append(source)
    docs=[g for (_,kind),g in groups.items() if kind!='web']
    web=[g for (_,kind),g in groups.items() if kind=='web']
    chosen=(docs[:2]+web[:3]) if docs and web else (docs+web)[:5]
    for group in chosen:
        for passage in retrieve(question,group,limit=1):
            passage.id='s'+str(len(result)+1)
            passage.text=passage.text[:min(1300,remaining)]
            if passage.text:result.append(passage);remaining-=len(passage.text)
    return result

@app.post('/api/estimate')
def estimate_cost(payload:AnalyzeRequest):
    return estimate(payload,select_sources(payload.question,payload.sources))

if (ROOT/'dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
