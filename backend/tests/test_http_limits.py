import asyncio
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.http_limits import BodyLimitMiddleware,MAX_BODY_BYTES,network_ip

def request(peer='192.0.2.1',headers=()):
    return Request({'type':'http','client':(peer,1234),'headers':[(k.encode(),v.encode()) for k,v in headers]})

def test_unconfigured_forwarded_headers_cannot_change_network(monkeypatch):
    monkeypatch.setenv('TRUSTED_PROXY_HOPS','0')
    assert network_ip(request(headers=[('x-forwarded-for','203.0.113.9')]))=='192.0.2.1'

def test_only_configured_proxy_suffix_is_trusted(monkeypatch):
    monkeypatch.setenv('TRUSTED_PROXY_HOPS','2');monkeypatch.setenv('TRUSTED_PROXY_CIDRS','10.0.0.0/8')
    trusted=request('10.0.0.1',[('x-forwarded-for','203.0.113.99, 198.51.100.1, 10.0.0.2')])
    assert network_ip(trusted)=='198.51.100.1'
    duplicate=request('10.0.0.1',[('x-forwarded-for','spoofed'),('x-forwarded-for','198.51.100.1,10.0.0.2')])
    assert network_ip(duplicate)=='198.51.100.1'
    with pytest.raises(HTTPException):network_ip(request(headers=[('x-forwarded-for','198.51.100.1,10.0.0.2')]))
    with pytest.raises(HTTPException):network_ip(request('10.0.0.1',[('x-forwarded-for','invalid')]))

def test_large_declared_and_streamed_bodies_are_blocked_before_app():
    calls=[];sent=[]
    async def app(scope,receive,send):calls.append(True)
    middleware=BodyLimitMiddleware(app)
    async def run():
        messages=iter([{'type':'http.request','body':b'x'*150000,'more_body':True},{'type':'http.request','body':b'x'*150000,'more_body':False}])
        async def receive():return next(messages)
        async def send(message):sent.append(message)
        await middleware({'type':'http','method':'POST','path':'/api/analyze','headers':[]},receive,send)
    asyncio.run(run())
    assert not calls and sent[0]['status']==413

def test_normal_api_body_still_reaches_validation():
    from app.main import app
    with TestClient(app) as client:
        assert client.post('/api/estimate',json={'question':'Which is preferable?','perspectives':['a','b']}).status_code==200
        assert client.post('/api/estimate',content='x'*(MAX_BODY_BYTES+1),headers={'content-type':'application/json'}).status_code==413
