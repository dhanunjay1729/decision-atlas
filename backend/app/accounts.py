"""Verify Google-managed user identities before private history access.

Passwords and refresh tokens never pass through this API. The Firebase Admin
SDK validates signed ID tokens, project audience, issuer, expiry and revocation.
"""
import os
from threading import Lock
from functools import lru_cache
from fastapi import HTTPException,Request

def auth_config():
    project=os.getenv('FIREBASE_PROJECT_ID','')
    key=os.getenv('FIREBASE_WEB_API_KEY','')
    return {'enabled':bool(project and key),'projectId':project,'apiKey':key,
            'authDomain':os.getenv('FIREBASE_AUTH_DOMAIN') or project+'.firebaseapp.com',
            'googleEnabled':os.getenv('FIREBASE_GOOGLE_ENABLED')=='true'}

_admin_lock=Lock()

@lru_cache(maxsize=1)
def admin_app():
    import firebase_admin
    with _admin_lock:
        try:return firebase_admin.get_app('decision-atlas-accounts')
        except ValueError:return firebase_admin.initialize_app(options={'projectId':os.environ['FIREBASE_PROJECT_ID']},name='decision-atlas-accounts')

def verify_token(token):
    from firebase_admin import auth
    return auth.verify_id_token(token,app=admin_app(),check_revoked=True)

def verified_claims(request:Request,required=False):
    cached=getattr(request.state,'account_claims',False)
    if cached is not False:
        if required and cached is None:raise HTTPException(401,'Sign in to view your private debates.')
        return cached
    header=request.headers.get('authorization','')
    if not header:
        request.state.account_claims=None
        if required:raise HTTPException(401,'Sign in to view your private debates.')
        return None
    if not auth_config()['enabled']:raise HTTPException(503,'Account services are unavailable.')
    if not header.startswith('Bearer ') or len(header)>16384:
        raise HTTPException(401,'Your session is invalid. Please sign in again.')
    try:
        claims=verify_token(header[7:])
        uid=claims.get('uid') or claims.get('sub')
        if not isinstance(uid,str) or not 1<=len(uid)<=128:raise ValueError('invalid identity')
        claims['uid']=uid
        request.state.account_claims=claims
        return claims
    except Exception:
        raise HTTPException(401,'Your session expired or is invalid. Please sign in again.') from None

def user_id(request:Request,required=False):
    claims=verified_claims(request,required)
    return claims['uid'] if claims else None
