"""Provider-neutral structured generation. No model is selected by default."""
import json
import os
from typing import TypeVar
from urllib.parse import quote, urlparse
import httpx
from pydantic import BaseModel
from .budget import Ledger

T = TypeVar('T', bound=BaseModel)

class ProviderError(Exception):
    pass

def configuration() -> dict:
    provider = os.getenv('MODEL_PROVIDER', 'unconfigured')
    name = os.getenv('MODEL_NAME', '')
    key = os.getenv('MODEL_API_KEY', '')
    prices = [os.getenv('MODEL_INPUT_USD_PER_MILLION'), os.getenv('MODEL_OUTPUT_USD_PER_MILLION')]
    try:
        valid_prices = all(p is not None and 0 <= float(p) < 1000 for p in prices)
    except ValueError:
        valid_prices = False
    base = os.getenv('MODEL_BASE_URL', '')
    valid_url = urlparse(base).scheme == 'https' and bool(urlparse(base).netloc)
    configured = bool(name and key and valid_prices and (provider == 'gemini' or provider == 'openai_compatible' and valid_url))
    return {'configured': configured, 'model': name if configured else None, 'provider': provider, 'web_available': False}

class ModelProvider:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    async def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        if not configuration()['configured']:
            raise ProviderError('No model is configured. Choose a provider, model, API key, and token prices first.')
        input_price = float(os.environ['MODEL_INPUT_USD_PER_MILLION'])
        output_price = float(os.environ['MODEL_OUTPUT_USD_PER_MILLION'])
        max_output = int(os.getenv('MAX_OUTPUT_TOKENS', '1800'))
        schema_json = schema.model_json_schema()
        # UTF-8 bytes are a conservative text token estimate for supported byte-based tokenizers.
        input_bound = len((system+prompt+json.dumps(schema_json)).encode('utf-8')) + 4096
        reservation = self.ledger.reserve((input_bound*input_price + max_output*output_price)/1_000_000)
        try:
            async with httpx.AsyncClient(timeout=75) as client:
                if os.environ['MODEL_PROVIDER'] == 'gemini':
                    # Key is sent in a header, never a URL or browser response.
                    r = await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{quote(os.environ["MODEL_NAME"], safe="")}:generateContent', headers={'x-goog-api-key':os.environ['MODEL_API_KEY']}, json={'systemInstruction':{'parts':[{'text':system}]}, 'contents':[{'role':'user','parts':[{'text':prompt}]}], 'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':schema_json,'maxOutputTokens':max_output}})
                    r.raise_for_status()
                    data = r.json()
                    candidate = data.get('candidates', [{}])[0]
                    if candidate.get('finishReason') != 'STOP':
                        raise ProviderError('The model did not finish a structured response. Please review its output limits.')
                    content = ''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
                    usage = data.get('usageMetadata', {})
                    input_tokens = usage.get('promptTokenCount')
                    output_tokens = usage.get('candidatesTokenCount',0) + usage.get('thoughtsTokenCount',0)
                else:
                    r = await client.post(os.environ['MODEL_BASE_URL'].rstrip('/')+'/chat/completions', headers={'Authorization':'Bearer '+os.environ['MODEL_API_KEY']}, json={'model':os.environ['MODEL_NAME'],'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],'max_tokens':max_output,'response_format':{'type':'json_schema','json_schema':{'name':schema.__name__,'strict':True,'schema':strict_schema(schema_json)}}})
                    r.raise_for_status()
                    data = r.json()
                    choice = data['choices'][0]
                    if choice.get('finish_reason') != 'stop':
                        raise ProviderError('The model did not finish a structured response. Please review its output limits.')
                    content = choice['message']['content']
                    usage = data.get('usage', {})
                    input_tokens = usage.get('prompt_tokens')
                    output_tokens = usage.get('completion_tokens')
                if input_tokens is not None and output_tokens is not None:
                    self.ledger.settle(reservation, (input_tokens*input_price + output_tokens*output_price)/1_000_000)
                return schema.model_validate_json(content)
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
            # Provider errors may contain sensitive request details; never forward their body.
            raise ProviderError('The model request failed or returned invalid structured data. Review server configuration.') from e

def strict_schema(value):
    if isinstance(value, list):
        return [strict_schema(x) for x in value]
    if not isinstance(value, dict):
        return value
    result = {k:strict_schema(v) for k,v in value.items()}
    if result.get('type') == 'object':
        result['additionalProperties'] = False
        result['required'] = list(result.get('properties', {}))
    return result
