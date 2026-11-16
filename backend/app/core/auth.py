from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Annotated

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, UserRole

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    # Retained only for compatibility with old administrative code; Cognito owns passwords.
    return password_hash.hash(password)

def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded: return False
    try: return password_hash.verify(password, encoded)
    except Exception: return False

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(user: User) -> str:
    raise RuntimeError("Local JWT issuance is disabled. Authenticate with Amazon Cognito.")

def set_refresh_cookie(*args, **kwargs):
    raise RuntimeError("Application refresh cookies are disabled; use Cognito fetchAuthSession().")

def clear_refresh_cookie(*args, **kwargs):
    return None

def verify_same_origin(*args, **kwargs):
    return None

@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.cognito_user_pool_id:
        raise RuntimeError("COGNITO_USER_POOL_ID is not configured")
    url = f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}/.well-known/jwks.json"
    return PyJWKClient(url, cache_keys=True, lifespan=3600)

def _decode_cognito_access_token(token: str) -> dict:
    if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
        raise HTTPException(status_code=503, detail="Cognito authentication is not configured")
    issuer = f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=issuer, options={"verify_aud": False})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired Cognito access token")
    if claims.get("token_use") != "access":
        raise HTTPException(status_code=401, detail="A Cognito access token is required")
    if claims.get("client_id") != settings.cognito_app_client_id:
        raise HTTPException(status_code=401, detail="Token was issued to a different Cognito app client")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Cognito token has no subject")
    return claims

def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Session = Depends(get_db)) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    claims = _decode_cognito_access_token(credentials.credentials)
    subject = claims["sub"]
    # Identities must be linked explicitly before rollout using the supplied sync script.
    # Do not auto-link by an unverified username/email claim from an access token.
    user = db.scalar(select(User).where(User.cognito_sub == subject))
    if user is None or not user.active:
        raise HTTPException(status_code=403, detail="Cognito identity is not linked to an active ThinkSmart user")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return user

def require_lead_access(user: User, lead) -> None:
    if user.role != UserRole.ADMIN and lead.assigned_to != user.id:
        raise HTTPException(status_code=404, detail="Lead not found")
