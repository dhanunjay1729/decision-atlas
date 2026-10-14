"""Fixed inexpensive model pool. No arbitrary model or provider fallbacks."""
import asyncio
import json
import math
import os
import time
import httpx
from .providers import ProviderError, safe_http_error, strict_schema
from .models import ArgumentOutput, PerspectiveOutput, ReportOutput, VerificationOutput

POOL = {
    'qwen': ('alibaba/qwen3.7-flash', 'alibaba', .03, .13),
    'dense': ('alibaba/qwen3.8-27b', 'runinfra', .10, .40),
    'haiku': ('anthropic/claude-haiku-5.5', 'anthropic', .10, .50),
    'crosscheck': ('openai/gpt-oss-20b', 'deepinfra', .03, .14),
}

class GatewayProvider:
    def __init__(self, ledger):
        self.ledger = ledger
        self.locks = {name: asyncio.Lock() for name in POOL}
        self.last_call = {}

    def for_stage(self, stage, request=None, agent=0):
        key = 'qwen' if stage == 'prepare' else 'haiku'
        if stage == 'argument':
            key = ('haiku' if agent == 1 else 'qwen') if request.include_web else 'dense'
        if stage == 'crosscheck': key = 'crosscheck'
        return ScopedGateway(self, key, stage)

    async def generate(self, system, prompt, schema):
        return await self.for_stage('prepare' if schema is PerspectiveOutput else 'report').generate(system,prompt,schema)

class ScopedGateway:
    def __init__(self, parent, key, stage):
        self.parent, self.key, self.stage = parent, key, stage
        self.model = POOL[key][0]

    async def generate(self, system, prompt, schema):
        model, provider, ip, op = POOL[self.key]
        cap = 600 if schema is PerspectiveOutput else (1400 if schema is ArgumentOutput else 2400)
        if schema is ReportOutput: cap = 1800
        js = strict_schema(schema.model_json_schema())
        messages = [{'role':'system','content':system+'\nReturn JSON matching all fields and limits: '+json.dumps(js)}, {'role':'user','content':prompt}]
        input_bound = len(json.dumps(messages).encode()) + 4096
        if input_bound > 64000:
            raise ProviderError('The debate context is too large. Reduce the documents or participant count.',422)
        # Reserve additional reasoning for OSS; failed calls keep their reservation.
        thinking = 65536 if self.key == 'crosscheck' else 0
        maximum = (input_bound*ip + (cap+thinking)*op)/1e6
        payload = {'model':model,'messages':messages,'max_tokens':cap,'stream':False,
                   'reasoning':{'effort':'low'} if thinking else {'enabled':False},
                   'providerOptions':{'gateway':{'only':[provider]}},
                   'response_format':{'type':'json_schema','json_schema':{'name':schema.__name__,'strict':True,'schema':js}}}
        async with self.parent.locks[self.key]:
            pause = max(0, (4 if self.key=='dense' else 1) - (time.monotonic()-self.parent.last_call.get(self.key,0)))
            if pause: await asyncio.sleep(pause)
            reservation = self.parent.ledger.reserve(maximum)
            self.parent.last_call[self.key] = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post('https://ai-gateway.vercel.sh/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['AI_GATEWAY_API_KEY']},json=payload)
                if not response.is_success: raise safe_http_error(response.status_code)
                data=response.json();usage=data.get('usage',{})
                if usage.get('cost') is not None:
                    cost=float(usage['cost'])
                    if not math.isfinite(cost) or cost<0: raise ValueError('Invalid usage')
                    self.parent.ledger.settle(reservation,cost)
                elif 'prompt_tokens' in usage and 'completion_tokens' in usage:
                    self.parent.ledger.settle(reservation,(usage['prompt_tokens']*ip+usage['completion_tokens']*op)/1e6)
                choice=data['choices'][0]
                if choice.get('finish_reason')!='stop': raise ProviderError('The model reached its output limit. No completed result is claimed.')
                content=choice['message']['content']
                if schema is ArgumentOutput:
                    raw=json.loads(content)
                    # A display label may be shortened without altering argument/claims.
                    if len(raw.get('position',''))>120:raw['position']=raw['position'][:100].rsplit(' ',1)[0]+'…'
                    return schema.model_validate(raw)
                return schema.model_validate_json(content)
            except httpx.HTTPError:
                raise ProviderError('Could not reach the model service. Try again later.',503) from None
            except (KeyError,ValueError,TypeError,IndexError):
                raise ProviderError('The model returned invalid structured output. No completed result is claimed.') from None

def estimate(request, sources):
    count=len(request.perspectives)
    text=sum(len(s.text) for s in sources)
    if request.include_web:text=max(text,5200)
    # Planning estimate, separate from conservative pre-request cost reservations.
    input_tokens=700+text/3.5+count*220
    output_tokens=320
    keys=[('haiku' if i==1 else 'qwen') if request.include_web else 'dense' for i in range(count)]
    drafts=sum(2*(input_tokens*POOL[k][2]+output_tokens*POOL[k][3])/1e6 for k in keys)
    checks=(input_tokens*.13+count*400*.64)/1e6 if sources or request.include_web else 0
    report=(input_tokens*.1+850*.5)/1e6
    expected=drafts+checks+report+(.0055 if request.include_web else 0)
    return {'estimated_usd':round(expected,5),'planning_upper_usd':round(expected*1.6,5),
            'target_average_usd':.02,'participants':count,'rounds':2,'argument_calls':count*2,
            'search_calls':int(request.include_web),'note':'Estimate only. Context, reasoning, corrections and provider failures can change charges. A persistent $2 project budget is enforced.'}
