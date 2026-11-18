from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, UserRole

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

COGNITO_GROUPS = {"SUPER_ADMIN", "ADMIN", "MANAGER", "SELLER", "VIEWER"}
GROUP_ROLE = {
    "SUPER_ADMIN": UserRole.SUPER_ADMIN,
    "ADMIN": UserRole.ADMIN,
    "MANAGER": UserRole.MANAGER,
    "SELLER": UserRole.SELLER,
    "VIEWER": UserRole.VIEWER,
}
ROLE_PRIORITY = ["SUPER_ADMIN", "ADMIN", "MANAGER", "SELLER", "VIEWER"]

@dataclass(frozen=True)
class CognitoPrincipal:
    sub: str
    email: str
    username: str
    name: str
    groups: frozenset[str]
    role: UserRole

    @property
    def is_admin(self) -> bool:
        return bool(self.groups.intersection({"SUPER_ADMIN", "ADMIN"}))

    @property
    def can_manage_team(self) -> bool:
        return bool(self.groups.intersection({"SUPER_ADMIN", "ADMIN", "MANAGER"}))


def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(*args, **kwargs):
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

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CognitoPrincipal:
    """Authenticate solely with Cognito. No PostgreSQL dependency is created here."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    claims = _decode_cognito_access_token(credentials.credentials)
    groups_claim = claims.get("cognito:groups") or []
    if isinstance(groups_claim, str):
        groups_claim = [groups_claim]
    groups = frozenset(g for g in groups_claim if g in COGNITO_GROUPS)
    if not groups:
        raise HTTPException(status_code=403, detail="Your Cognito account has no ThinkSmart access group")
    role_name = next(g for g in ROLE_PRIORITY if g in groups)
    return CognitoPrincipal(
        sub=claims["sub"],
        email=(claims.get("email") or "").strip().lower(),
        username=claims.get("cognito:username") or claims.get("username") or claims["sub"],
        name=claims.get("name") or claims.get("given_name") or claims.get("email") or "ThinkSmart user",
        groups=groups,
        role=GROUP_ROLE[role_name],
    )

def get_business_user(
    principal: CognitoPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Resolve/create a DB profile only for business operations; never used by login or /auth/me."""
    email = principal.email
    full_name = principal.name
    if not email:
        # Cognito access tokens do not always contain email/name. Fetch these
        # attributes only when a DB-backed business operation needs a profile.
        try:
            import boto3
            cognito_user = boto3.client("cognito-idp", region_name=settings.aws_region).admin_get_user(
                UserPoolId=settings.cognito_user_pool_id,
                Username=principal.username,
            )
            attrs = {item["Name"]: item["Value"] for item in cognito_user.get("UserAttributes", [])}
            email = (attrs.get("email") or "").strip().lower()
            full_name = attrs.get("name") or full_name
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not load Cognito profile: {type(exc).__name__}")
    if not email:
        raise HTTPException(status_code=403, detail="Cognito account has no email attribute")
    user = db.scalar(select(User).where(User.cognito_sub == principal.sub))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.cognito_sub not in (None, principal.sub):
            raise HTTPException(status_code=409, detail="Email is already linked to another Cognito identity")
        if user is None:
            user = User(
                email=email,
                full_name=full_name[:160],
                role=principal.role,
                active=True,
                cognito_sub=principal.sub,
                password_hash=None,
                must_change_password=False,
            )
            db.add(user)
        else:
            user.cognito_sub = principal.sub
    user.email = email
    user.full_name = full_name[:160] or user.full_name
    user.role = principal.role
    user.active = True
    db.commit()
    db.refresh(user)
    return user

def require_admin(principal: CognitoPrincipal = Depends(get_current_user)) -> CognitoPrincipal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return principal

def require_admin_user(
    principal: CognitoPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    return get_business_user(principal, db)

def require_lead_access(user: User, lead) -> None:
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN} and lead.assigned_to != user.id:
        raise HTTPException(status_code=404, detail="Lead not found")
