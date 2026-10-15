"""Owner role requires a server-verified Google sign-in for the configured email."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app import accounts, owner

OWNER='pantadhanunjay@gmail.com'


def request(headers=()):
    return Request({'type':'http','headers':list(headers)})


def claims(**changes):
    return {'email':OWNER,'email_verified':True,
            'firebase':{'sign_in_provider':'google.com'},**changes}


def mocked_identity(monkeypatch,value):
    monkeypatch.setenv('OWNER_GOOGLE_EMAIL',OWNER)
    monkeypatch.setattr(accounts,'verified_claims',lambda request:value)


def test_verified_owner_google_login_grants_owner(monkeypatch):
    mocked_identity(monkeypatch,claims())
    assert owner.is_owner(request()) is True
    mocked_identity(monkeypatch,claims(email='PANTADHANUNJAY@gmail.com'))
    assert owner.is_owner(request()) is True


@pytest.mark.parametrize('identity',[
    None,{},'unverified',
    claims(email='another@gmail.com'),
    claims(email=OWNER+' '),
    claims(email=123),
    claims(email_verified=False),
    claims(email_verified='true'),
    claims(email_verified=1),
    claims(firebase={'sign_in_provider':'password'}),
    claims(firebase={'sign_in_provider':'anonymous'}),
    claims(firebase={}),
    claims(firebase=None),
])
def test_unverified_or_different_identity_has_no_owner_privileges(monkeypatch,identity):
    mocked_identity(monkeypatch,identity)
    assert owner.is_owner(request()) is False


def test_missing_owner_configuration_denies_every_identity(monkeypatch):
    mocked_identity(monkeypatch,claims())
    monkeypatch.delenv('OWNER_GOOGLE_EMAIL')
    assert owner.is_owner(request()) is False


@pytest.mark.parametrize('status',[401,503])
def test_invalid_or_unavailable_auth_denies_owner(monkeypatch,status):
    monkeypatch.setenv('OWNER_GOOGLE_EMAIL',OWNER)
    def invalid(request):raise HTTPException(status,'Invalid identity')
    monkeypatch.setattr(accounts,'verified_claims',invalid)
    assert owner.is_owner(request()) is False


def test_legacy_owner_secret_cookie_or_raw_email_never_grants_access(monkeypatch):
    mocked_identity(monkeypatch,None)
    monkeypatch.setenv('ATLAS_OWNER_TOKEN','a'*48)
    headers=[(b'cookie',b'atlas_owner=forged'),
             (b'authorization',b'Bearer '+b'a'*48),
             (b'x-owner-email',OWNER.encode())]
    assert owner.is_owner(request(headers)) is False
