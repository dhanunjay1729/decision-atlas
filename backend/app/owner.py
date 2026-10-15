"""Owner login with a server secret and short-lived signed, HttpOnly sessions."""
import hashlib,hmac,os,secrets,time
from fastapi import Request

COOKIE='atlas_owner'
TTL=12*3600

def secret():return os.getenv('ATLAS_OWNER_TOKEN','')

def valid_token(token):
    key=secret()
    return len(key)>=32 and hmac.compare_digest(token,key)

def session():
    payload=f'{int(time.time())+TTL}.{secrets.token_hex(16)}'
    return payload+'.'+hmac.new(secret().encode(),payload.encode(),hashlib.sha256).hexdigest()

def is_owner(request:Request):
    if len(secret())<32:return False
    value=request.cookies.get(COOKIE,'')
    try:
        expires,nonce,signature=value.split('.')
        payload=expires+'.'+nonce
        expected=hmac.new(secret().encode(),payload.encode(),hashlib.sha256).hexdigest()
        return time.time()<int(expires)<=time.time()+TTL and hmac.compare_digest(signature,expected)
    except (ValueError,TypeError):return False
