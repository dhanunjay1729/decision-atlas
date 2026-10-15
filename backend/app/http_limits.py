"""Bound API body size and resolve client identity only through configured proxies."""
import ipaddress,os
from fastapi import HTTPException
from starlette.responses import JSONResponse

MAX_BODY_BYTES=256_000

class BodyLimitMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method')!='POST' or not scope.get('path','').startswith('/api/'):
            return await self.app(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            body.extend(message.get('body',b''))
            if len(body)>MAX_BODY_BYTES:
                return await JSONResponse({'detail':'This request is too large. Reduce the pasted text or documents.'},413)(scope,receive,send)
            if not message.get('more_body',False):break
        consumed=False
        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)

def network_ip(request):
    peer=request.client.host if request.client else 'unknown'
    try:
        hops=int(os.getenv('TRUSTED_PROXY_HOPS','0'))
        if not 0<=hops<=8:raise ValueError()
    except ValueError:raise HTTPException(503,'Invalid trusted proxy configuration.') from None
    if not hops:return peer
    try:
        address=ipaddress.ip_address(peer)
        networks=[ipaddress.ip_network(x.strip()) for x in os.getenv('TRUSTED_PROXY_CIDRS','').split(',') if x.strip()]
        if not networks or not any(address in n for n in networks):
            raise ValueError('Untrusted proxy')
        # Join duplicate header lines in their received order, then count from the trusted end.
        chain=','.join(request.headers.getlist('x-forwarded-for')).split(',')
        if len(chain)<hops:raise ValueError('Missing proxy hops')
        return str(ipaddress.ip_address(chain[-hops].strip()))
    except ValueError:
        raise HTTPException(503,'Client network could not be verified. Review the trusted proxy configuration.') from None
