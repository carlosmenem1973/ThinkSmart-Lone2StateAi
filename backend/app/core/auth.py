from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, UserRole

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        # Perform a dummy hash verification to reduce account enumeration timing differences.
        password_hash.hash(password)
        return False
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "ver": user.token_version or 0,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("Wrong token type")
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Account is inactive or unavailable")
    if payload.get("ver", 0) != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Access token has been revoked", headers={"WWW-Authenticate": "Bearer"})
    if user.must_change_password and request.url.path not in {"/api/v1/auth/change-password", "/api/v1/auth/me"}:
        raise HTTPException(status_code=403, detail="Password change required before accessing the application")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return user

def require_lead_access(user: User, lead) -> None:
    if user.role != UserRole.ADMIN and lead.assigned_to != user.id:
        raise HTTPException(status_code=404, detail="Lead not found")

def cookie_is_secure() -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return settings.environment.lower() in {"prod", "production"}

def set_refresh_cookie(response, token: str) -> None:
    response.set_cookie(
        key="estateai_refresh", value=token, httponly=True, secure=cookie_is_secure(),
        samesite="strict", path="/api/v1/auth", max_age=settings.refresh_token_days * 86400,
    )

def clear_refresh_cookie(response) -> None:
    response.delete_cookie(key="estateai_refresh", path="/api/v1/auth", httponly=True, secure=cookie_is_secure(), samesite="strict")

def verify_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin != settings.frontend_origin.rstrip("/"):
        raise HTTPException(status_code=403, detail="Invalid request origin")
