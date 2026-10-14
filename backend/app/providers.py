"""Structured generation with explicit Gemini free-tier settings."""
import asyncio
import json
import os
import time
from typing import TypeVar
from urllib.parse import quote, urlparse
import httpx
from pydantic import BaseModel
from .budget import Ledger

T = TypeVar('T', bound=BaseModel)
FREE_GEMINI_MODELS = {'gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3-flash-preview'}

class ProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code

def free_tier_only() -> bool:
    return os.getenv('GEMINI_FREE_TIER_ONLY', 'false').lower() == 'true'

def configuration() -> dict:
    provider = os.getenv('MODEL_PROVIDER', 'unconfigured')
    if provider == 'vercel':
        configured = bool(os.getenv('AI_GATEWAY_API_KEY'))
        return {'configured':configured,'model':'Affordable multi-model pool' if configured else None,'prepare_model':'alibaba/qwen3.7-flash' if configured else None,'provider':'vercel','free_tier_only':False,'web_available':configured}

    name = os.getenv('MODEL_NAME', '')
    prepare_model = os.getenv('MODEL_PREPARE_NAME', '') or name
    prices = [os.getenv('MODEL_INPUT_USD_PER_MILLION'), os.getenv('MODEL_OUTPUT_USD_PER_MILLION')]
    try:
        valid_prices = all(p is not None and 0 <= float(p) < 1000 for p in prices)
        free_valid = not free_tier_only() or (provider == 'gemini' and name in FREE_GEMINI_MODELS and prepare_model in FREE_GEMINI_MODELS and all(float(p or '-1') == 0 for p in prices))
    except ValueError:
        valid_prices = free_valid = False
    base = urlparse(os.getenv('MODEL_BASE_URL', ''))
    valid_url = base.scheme == 'https' and bool(base.netloc) and not base.username and not base.password
    configured = bool(name and os.getenv('MODEL_API_KEY') and valid_prices and free_valid and (provider == 'gemini' or provider == 'openai_compatible' and valid_url))
    return {'configured': configured, 'model': name if configured else None, 'prepare_model': prepare_model if configured else None, 'provider': provider, 'free_tier_only': free_tier_only(), 'web_available': False}

def safe_http_error(status: int) -> ProviderError:
    # Never expose provider response bodies, headers, or credentials.
    if status == 429:
        return ProviderError('Model quota reached. Wait for the quota reset or reduce usage. No paid fallback was used.', 429)
    if status in (401, 403):
        return ProviderError('The model credential or project access was rejected. Check the server-side key and API restrictions.', 503)
    if status == 404:
        return ProviderError('The configured model is unavailable for this project. Choose an accessible model.', 503)
    if status in (500, 502, 503, 504):
        return ProviderError('The model service is temporarily unavailable. Try again later; no fallback was used.', 503)
    return ProviderError('The model rejected the request. Review its schema and generation settings.')

class ModelProvider:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self._lock = asyncio.Lock()
        self._last_call: dict[str, float] = {}

    async def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        config = configuration()
        if not config['configured']:
            raise ProviderError('No valid model configuration is available. Check the provider, key, model names, and token prices.', 503)
        model = config['prepare_model'] if schema.__name__ == 'PerspectiveOutput' else config['model']
        input_price = float(os.environ['MODEL_INPUT_USD_PER_MILLION'])
        output_price = float(os.environ['MODEL_OUTPUT_USD_PER_MILLION'])
        max_output = int(os.getenv('MAX_OUTPUT_TOKENS', '6000'))
        if schema.__name__ == 'PerspectiveOutput':
            max_output = min(max_output, 1800)
        if not 256 <= max_output <= 16000:
            raise ProviderError('MAX_OUTPUT_TOKENS must be between 256 and 16000.', 503)
        schema_json = schema.model_json_schema()
        input_bound = len((system + prompt + json.dumps(schema_json)).encode('utf-8')) + 4096
        if input_bound > 100000:
            raise ProviderError('The model prompt is too large. Reduce the evidence collection.', 422)
        async with self._lock:
            if config['provider'] == 'gemini':
                interval = max(0.0, min(float(os.getenv('GEMINI_MIN_REQUEST_INTERVAL_SECONDS', '6')), 60))
                remaining = interval - (time.monotonic() - self._last_call.get(model, 0))
                if remaining > 0:
                    await asyncio.sleep(remaining)
                self._last_call[model] = time.monotonic()
            reservation = self.ledger.reserve((input_bound * input_price + max_output * output_price) / 1_000_000)
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    if config['provider'] == 'gemini':
                        r = await client.post(
                            f'https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe="")}:generateContent',
                            headers={'x-goog-api-key': os.environ['MODEL_API_KEY']},
                            json={'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                                  'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': schema_json, 'maxOutputTokens': max_output,
                                                       'thinkingConfig': {'thinkingLevel': os.getenv('GEMINI_THINKING_LEVEL', 'low')}}},
                        )
                        if not r.is_success:
                            raise safe_http_error(r.status_code)
                        data = r.json()
                        usage = data.get('usageMetadata', {})
                        input_tokens = usage.get('promptTokenCount')
                        output_tokens = usage.get('candidatesTokenCount', 0) + usage.get('thoughtsTokenCount', 0)
                        if input_tokens is not None:
                            self.ledger.settle(reservation, (input_tokens * input_price + output_tokens * output_price) / 1_000_000)
                        candidates = data.get('candidates') or []
                        if not candidates:
                            raise ProviderError('The model returned no usable answer. The request may have been blocked.')
                        candidate = candidates[0]
                        if candidate.get('finishReason') != 'STOP':
                            raise ProviderError('The model response was blocked or reached its output limit. No completed analysis is claimed.')
                        content = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
                    else:
                        r = await client.post(os.environ['MODEL_BASE_URL'].rstrip('/') + '/chat/completions', headers={'Authorization': 'Bearer ' + os.environ['MODEL_API_KEY']},
                                              json={'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}], 'max_tokens': max_output,
                                                    'response_format': {'type': 'json_schema', 'json_schema': {'name': schema.__name__, 'strict': True, 'schema': strict_schema(schema_json)}}})
                        if not r.is_success:
                            raise safe_http_error(r.status_code)
                        data = r.json()
                        usage = data.get('usage', {})
                        input_tokens, output_tokens = usage.get('prompt_tokens'), usage.get('completion_tokens')
                        if input_tokens is not None and output_tokens is not None:
                            self.ledger.settle(reservation, (input_tokens * input_price + output_tokens * output_price) / 1_000_000)
                        choice = data['choices'][0]
                        if choice.get('finish_reason') != 'stop':
                            raise ProviderError('The model did not finish a structured response. Review its output limit.')
                        content = choice['message']['content']
                    return schema.model_validate_json(content)
            except httpx.HTTPError:
                raise ProviderError('Could not reach the model service. Please try again later.', 503) from None
            except (KeyError, ValueError, IndexError, TypeError):
                raise ProviderError('The model returned invalid structured data. No completed analysis is claimed.') from None

def strict_schema(value):
    if isinstance(value, list):
        return [strict_schema(x) for x in value]
    if not isinstance(value, dict):
        return value
    result = {k: strict_schema(v) for k, v in value.items()}
    if result.get('type') == 'object':
        result['additionalProperties'] = False
        result['required'] = list(result.get('properties', {}))
    return result
