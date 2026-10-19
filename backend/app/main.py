import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .budget import configured_ledger, LimitError
from .engine import SYSTEM, debate
from .models import AnalyzeRequest, PrepareRequest, PerspectiveOutput
from .providers import ModelProvider, ProviderError, configuration
from .retrieval import retrieve
from .gateway import GatewayProvider, estimate
from .search import search
from .http_limits import BodyLimitMiddleware,network_ip
from .owner import is_owner
from .featured import create_store, FeaturedError
from pydantic import BaseModel, Field
from .accounts import auth_config, user_id
from .history import create_history, HistoryError

app = FastAPI(title='Decision Atlas', version='0.1.0')
app.add_middleware(BodyLimitMiddleware)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env', override=False)
ledger = configured_ledger(ROOT)
provider = GatewayProvider(ledger) if os.getenv('MODEL_PROVIDER')=='vercel' else ModelProvider(ledger)
run_lock = asyncio.Semaphore(1)
featured_store = create_store(ROOT, ledger)
history_store = create_history(ROOT, ledger)

@app.get('/api/status')
def status():
    return configuration()

@app.get('/api/allowance')
def allowance(request:Request):
    try:
        daily=ledger.daily_status()
        return {**({'limit':None,'used':0,'remaining':None} if is_owner(request) else ledger.allowance(network_ip(request))), 'owner':is_owner(request), 'daily':daily}
    except LimitError as e:raise HTTPException(503,str(e)) from None

def available(request: Request):
    if not configuration()['configured']:
        raise HTTPException(503, 'Live analysis is not connected yet. Explore the labeled sample while a model is selected.')
    try:
        # Do not trust X-Forwarded-For. Configure the ASGI proxy allowlist for hosting.
        ip=network_ip(request)
        if not ledger.daily_status()['available']:
            raise LimitError('Live debates are paused for today. Please return after the daily reset.')
        if not is_owner(request) and ledger.allowance(ip)['remaining']==0:
            raise LimitError('This network has used its five-debate allowance. The saved sample remains available.')
        if not is_owner(request):ledger.request(ip)
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
    uid=user_id(request)
    sources = select_sources(payload.question,payload.sources)
    available(request)
    async def events():
        async with run_lock:
            try:
                if await request.is_disconnected(): return
                if not is_owner(request):ledger.start_debate(network_ip(request))
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
                        try:event['analysis']['publish_token'] = featured_store.save_completed(event['analysis'])
                        except FeaturedError:pass  # Sharing availability must not discard a completed paid debate.
                        if uid:
                            try:
                                event['analysis']['history_id']=history_store.save_completed(uid,event['analysis'])
                                event['analysis']['history_saved']=True
                            except HistoryError as error:
                                event['analysis']['history_saved']=False
                                event['analysis']['history_notice']=str(error)
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

@app.get('/api/auth/config')
def public_auth_config():return auth_config()

def history_call(callback):
    try:return callback()
    except HistoryError as error:raise HTTPException(error.status_code,str(error)) from None

@app.get('/api/history')
def history_list(request:Request):
    uid=user_id(request,required=True)
    return history_call(lambda:history_store.list(uid))

@app.get('/api/history/{entry_id}')
def history_get(entry_id:str,request:Request):
    uid=user_id(request,required=True)
    return history_call(lambda:history_store.get(uid,entry_id))

@app.post('/api/history/{entry_id}/hide')
def history_hide(entry_id:str,request:Request):
    uid=user_id(request,required=True)
    return history_call(lambda:history_store.hide(uid,entry_id))

class Publication(BaseModel):
    publish_token: str = Field(min_length=1,max_length=256)
    consent: bool = False

class ShareConsent(BaseModel):
    consent: bool = False

def featured_call(callback):
    try:return callback()
    except FeaturedError as e:raise HTTPException(getattr(e,'status_code',400),str(e)) from None

@app.post('/api/history/{entry_id}/publish')
def history_publish(entry_id:str,payload:ShareConsent,request:Request):
    uid=user_id(request,required=True)
    entry=history_call(lambda:history_store.get(uid,entry_id))
    return featured_call(lambda:featured_store.publish_saved(entry_id,entry['analysis'],consent=payload.consent))

@app.get('/api/featured')
def featured_list():return featured_call(lambda:featured_store.list())

@app.post('/api/featured')
def featured_publish(payload:Publication):
    return featured_call(lambda:featured_store.publish(payload.publish_token,consent=payload.consent))

@app.get('/api/featured/{entry_id}')
def featured_get(entry_id:str):return featured_call(lambda:featured_store.get(entry_id))

@app.post('/api/featured/{entry_id}/like')
def featured_like(entry_id:str,request:Request):
    return featured_call(lambda:featured_store.vote(entry_id,network_ip(request)))

@app.post('/api/featured/{entry_id}/hide')
def featured_hide(entry_id:str,request:Request):
    if not is_owner(request):raise HTTPException(403,'Owner access required.')
    return featured_call(lambda:featured_store.hide(entry_id))

@app.delete('/api/featured/{entry_id}')
def featured_delete(entry_id:str,request:Request):
    if not is_owner(request):raise HTTPException(403,'Admin Google sign-in required.')
    return featured_call(lambda:featured_store.delete(entry_id))

@app.get('/api/_deployment/network')
def deployment_network(request:Request):
    if os.getenv('ATLAS_DEPLOYMENT_DIAGNOSTICS')!='true':raise HTTPException(404,'Not found')
    return {'peer':request.client.host if request.client else None,'forwarded':request.headers.getlist('x-forwarded-for')}

if (ROOT/'dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
