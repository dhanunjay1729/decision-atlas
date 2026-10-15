"""Owner privileges derive only from a verified Google account identity."""
import os
from fastapi import HTTPException, Request
from . import accounts


def is_owner(request: Request) -> bool:
    expected = os.getenv('OWNER_GOOGLE_EMAIL', '').strip().casefold()
    if not expected:
        return False
    try:
        claims = accounts.verified_claims(request)
    except HTTPException:
        return False
    if not isinstance(claims, dict):
        return False
    firebase = claims.get('firebase')
    email = claims.get('email')
    return (
        claims.get('email_verified') is True
        and isinstance(email, str)
        and email.casefold() == expected
        and isinstance(firebase, dict)
        and firebase.get('sign_in_provider') == 'google.com'
    )
