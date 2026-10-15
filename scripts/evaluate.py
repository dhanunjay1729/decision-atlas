"""Explicitly opt-in paid smoke tests and a small matched-evidence baseline.

PYTHONPATH=backend .venv/bin/python scripts/evaluate.py --live --max-usd .06
Raw generated reports and excerpts stay in ignored work/; public summary has counts only.
This is a developer-authored fixture, not a held-out accuracy benchmark.
"""
import argparse,asyncio,json,os,time
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel,Field
from app.budget import Ledger
from app.engine import SYSTEM,CLASSIFY_TASK,VERIFY_TASK,apply_kinds,apply_verification,apply_crosscheck,verify_batches,debate
from app.gateway import GatewayProvider
from app.models import AnalyzeRequest,Claim,ClaimKindsOutput,Source
from app.providers import ProviderError
from app.search import search

ROOT=Path(__file__).resolve().parents[1]
class BaselineClaim(BaseModel):
    text:str=Field(min_length=1,max_length=500)
    kind:Literal['empirical','value']
    status:Literal['supported','contradicted','insufficient','value','unverified']
    source_ids:list[str]=Field(max_length=5)
class BaselineOutput(BaseModel):
    report:str=Field(min_length=100,max_length=10000)
    claims:list[BaselineClaim]=Field(min_length=1,max_length=10)

def score(claims,gold):
    expected={c['id']:c['status'] for c in gold}
    return {'exact':sum(c.status==expected[c.id] for c in claims),'review':sum(c.status=='review' for c in claims),'wrong_nonabstained':sum(c.status not in ('review',expected[c.id]) for c in claims),'total':len(claims)}

async def run(args):
    load_dotenv(ROOT/'.env',override=False)
    os.environ['TOTAL_MODEL_BUDGET_USD']=str(args.max_usd)
    output=ROOT/'work'/args.name;output.mkdir(parents=True,exist_ok=False)
    ledger=Ledger(str(output/'usage.sqlite3'));provider=GatewayProvider(ledger)
    summary={'version':1,'fixture_note':'Developer-authored, tiny smoke suite. Baseline is one Haiku call with matched selected evidence, not a cost-matched or strongest-possible single-agent system. Automated counts do not measure factual accuracy.','cases':[]}
    fixture=json.loads((ROOT/'evaluation/verification.json').read_text());source=Source(**fixture['source'])
    claims=[Claim(id=c['id'],agent=0,text=c['text'],source_ids=[]) for c in fixture['claims']]
    before=ledger.total()
    kinds=await provider.for_stage('classification').generate(SYSTEM,json.dumps({'task':CLASSIFY_TASK,'claims':[{'id':c.id,'text':c.text} for c in claims]}),ClaimKindsOutput)
    apply_kinds(claims,kinds,True)
    prompt=json.dumps({'task':VERIFY_TASK,'claims':[{'id':c.id,'text':c.text} for c in claims],'sources':[source.model_dump()]})
    first=await verify_batches(provider.for_stage('verification'),prompt)
    apply_verification(claims,[source],first)
    single=[c.model_copy(deep=True) for c in claims]
    second=await verify_batches(provider.for_stage('crosscheck'),prompt)
    apply_crosscheck(claims,[source],first,second)
    summary['verification']={'kind_correct':sum(c.kind==g['kind'] for c,g in zip(claims,fixture['claims'])),'kind_total':len(claims),'single_verifier':score(single,fixture['claims']),'crosschecked':score(claims,fixture['claims']),'accounted_usd':round(ledger.total()-before,6)}
    (output/'verification.json').write_text(json.dumps([c.model_dump() for c in claims],indent=2))
    print(json.dumps(summary['verification']),flush=True)
    for case in json.loads((ROOT/'evaluation/cases.json').read_text()):
        request=AnalyzeRequest(**{k:v for k,v in case.items() if k!='id'})
        before=ledger.total();started=time.monotonic();sources=request.sources
        if request.include_web:
            from app.main import select_sources
            sources=select_sources(request.question,await search(request.question,ledger))
        evidence_cost=ledger.total()-before
        raw={'sources':[s.model_dump() for s in sources],'events':[]};row={'id':case['id'],'participants':len(request.perspectives),'evidence_cost_usd':round(evidence_cost,6)}
        try:
            async for event in debate(request,sources,provider):
                raw['events'].append(event)
                if event['type']=='progress':print(case['id'],event['message'],flush=True)
            a=raw['events'][-1]['analysis']
            row['debate']={'completed':True,'arguments':len(a['arguments']),'claims':len(a['claims']),'report_words':len(a['report'].split()),'sources':len(sources),'statuses':{s:sum(c['status']==s for c in a['claims']) for s in sorted({c['status'] for c in a['claims']})},'accounted_usd':round(ledger.total()-before,6),'seconds':round(time.monotonic()-started,1)}
        except (ProviderError,ValueError) as error:
            row['debate']={'completed':False,'error':str(error),'accounted_usd':round(ledger.total()-before,6)}
        before=ledger.total();started=time.monotonic()
        try:
            baseline=await provider.for_stage('report').generate(SYSTEM,json.dumps({'task':'In a single response, write a balanced 300–500 word comparison of all supplied perspectives with no winner, recommendation or hybrid compromise. Distinguish factual assertions from value priorities. End with unresolved questions. Extract at most ten atomic claims and assess each against supplied passages. Effects on skills, learning or workload are empirical, not values. Unsupported source-free factual claims are unverified; with passages use insufficient. Only pure ethical preferences are value. Supported/contradicted require valid source IDs and exact passage support. Missing evidence is not proof of no effect.','question':request.question,'perspectives':request.perspectives,'sources':[s.model_dump() for s in sources]}),BaselineOutput)
            raw['baseline']=baseline.model_dump()
            row['baseline']={'completed':True,'claims':len(baseline.claims),'report_words':len(baseline.report.split()),'accounted_usd':round(ledger.total()-before+evidence_cost,6),'seconds':round(time.monotonic()-started,1),'model':'anthropic/claude-haiku-5.5'}
        except (ProviderError,ValueError) as error:row['baseline']={'completed':False,'error':str(error),'accounted_usd':round(ledger.total()-before+evidence_cost,6)}
        (output/(case['id']+'.json')).write_text(json.dumps(raw,indent=2));summary['cases'].append(row)
        summary['accounted_usd']=round(ledger.total(),6)
        (output/'summary.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps(row),flush=True)
    print('Saved',str(output/'summary.json'),'accounted_usd',ledger.total(),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Required: makes paid API calls')
    parser.add_argument('--max-usd',type=float,default=.06)
    parser.add_argument('--name',default='quality-review-2026-10-15')
    args=parser.parse_args()
    if not args.live:parser.error('No paid calls made. Pass --live to explicitly opt in.')
    if not 0<args.max_usd<=.08:parser.error('This small review is capped at $0.08.')
    asyncio.run(run(args))
