from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import boto3
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User, UserRole


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


# Canonical Cognito groups and their application roles.
GROUP_ROLE = {
    "SUPER_ADMIN": UserRole.SUPER_ADMIN,
    "ADMIN": UserRole.ADMIN,
    "MANAGER": UserRole.MANAGER,
    "SELLER": UserRole.SELLER,
    "VIEWER": UserRole.VIEWER,
}

ROLE_PRIORITY = (
    "SUPER_ADMIN",
    "ADMIN",
    "MANAGER",
    "SELLER",
    "VIEWER",
)

# Existing lowercase groups are normalized without renaming them in Cognito.
LEGACY_GROUP_ALIASES = {
    "SUPER_ADMIN": "SUPER_ADMIN",
    "ADMIN": "ADMIN",
    "MANAGER": "MANAGER",
    "SELLER": "SELLER",
    "VIEWER": "VIEWER",
}


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
        return bool(
            self.groups.intersection({"SUPER_ADMIN", "ADMIN"})
        )

    @property
    def can_manage_team(self) -> bool:
        return bool(
            self.groups.intersection(
                {"SUPER_ADMIN", "ADMIN", "MANAGER"}
            )
        )


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    encoded: str | None,
) -> bool:
    if not encoded:
        return False

    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def create_access_token(*args: Any, **kwargs: Any):
    raise RuntimeError(
        "Local JWT issuance is disabled. "
        "Authenticate with Amazon Cognito."
    )


def set_refresh_cookie(*args: Any, **kwargs: Any):
    raise RuntimeError(
        "Application refresh cookies are disabled. "
        "Use Cognito fetchAuthSession()."
    )


def clear_refresh_cookie(*args: Any, **kwargs: Any):
    return None


def verify_same_origin(*args: Any, **kwargs: Any):
    return None


def normalize_group(group: str) -> str | None:
    """
    Normalize Cognito group casing without modifying Cognito groups.
    Unknown legacy groups are deliberately not granted a role.
    """
    normalized = group.strip().upper()

    return LEGACY_GROUP_ALIASES.get(normalized)


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.cognito_user_pool_id:
        raise RuntimeError(
            "COGNITO_USER_POOL_ID is not configured"
        )

    url = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )

    return PyJWKClient(
        url,
        cache_keys=True,
        lifespan=3600,
    )


def _decode_cognito_access_token(token: str) -> dict:
    if (
        not settings.cognito_user_pool_id
        or not settings.cognito_app_client_id
    ):
        raise HTTPException(
            status_code=503,
            detail="Cognito authentication is not configured",
        )

    issuer = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}"
    )

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Cognito access token",
        )

    if claims.get("token_use") != "access":
        raise HTTPException(
            status_code=401,
            detail="A Cognito access token is required",
        )

    if claims.get("client_id") != settings.cognito_app_client_id:
        raise HTTPException(
            status_code=401,
            detail="Token was issued to a different Cognito app client",
        )

    if not claims.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Cognito token has no subject",
        )

    return claims


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer),
    ],
) -> CognitoPrincipal:

    """
    Authenticate exclusively through Cognito.
    This dependency never opens a PostgreSQL session.
    """

    if (
        not credentials
        or credentials.scheme.lower() != "bearer"
    ):
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_cognito_access_token(
        credentials.credentials
    )

    raw_groups = claims.get("cognito:groups") or []

    if isinstance(raw_groups, str):
        raw_groups = [raw_groups]

    groups = frozenset(
        normalized
        for group in raw_groups
        if isinstance(group, str)
        and (normalized := normalize_group(group)) is not None
    )

    if not groups:
        raise HTTPException(
            status_code=403,
            detail="Your Cognito account has no ThinkSmart access group",
        )

    role_name = next(
        role for role in ROLE_PRIORITY
        if role in groups
    )

    return CognitoPrincipal(
        sub=claims["sub"],
        email=(claims.get("email") or "").strip().lower(),
        username=(
            claims.get("cognito:username")
            or claims.get("username")
            or claims["sub"]
        ),
        name=(
            claims.get("name")
            or claims.get("given_name")
            or claims.get("email")
            or "ThinkSmart user"
        ),
        groups=groups,
        role=GROUP_ROLE[role_name],
    )


def _load_cognito_profile(
    principal: CognitoPrincipal,
) -> tuple[str, str]:
    """
    Load the Cognito profile when the access token does not
    contain an email address.

    The returned Cognito sub must match the authenticated JWT.
    """

    try:
        client = boto3.client(
            "cognito-idp",
            region_name=settings.aws_region,
        )

        response = client.admin_get_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=principal.username,
        )

        attributes = {
            item["Name"]: item["Value"]
            for item in response.get("UserAttributes", [])
        }

        cognito_sub = attributes.get("sub")

        if cognito_sub != principal.sub:
            raise HTTPException(
                status_code=401,
                detail="Cognito identity verification failed",
            )

        email = (
            attributes.get("email") or ""
        ).strip().lower()

        full_name = (
            attributes.get("name")
            or attributes.get("given_name")
            or principal.name
        )

        return email, full_name

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not load Cognito profile: "
                f"{type(exc).__name__}"
            ),
        )


def get_business_user(
    principal: CognitoPrincipal = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:

    """
    Resolve the PostgreSQL business profile.

    Resolution order:
      1. Cognito sub.
      2. Normalized email.

    Never silently replace an existing Cognito identity.
    Never automatically reactivate a disabled user.
    """

    email = principal.email
    full_name = principal.name

    if not email:
        email, full_name = _load_cognito_profile(principal)

    if not email:
        raise HTTPException(
            status_code=403,
            detail="Cognito account has no email attribute",
        )

    try:
        # First: immutable Cognito subject.
        user = db.scalar(
            select(User).where(
                User.cognito_sub == principal.sub
            )
        )

        if user is None:
            # Second: normalized email.
            user = db.scalar(
                select(User).where(
                    func.lower(User.email) == email
                )
            )

            if user is not None:
                existing_sub = user.cognito_sub

                if existing_sub not in (None, "", principal.sub):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "COGNITO_IDENTITY_CONFLICT",
                            "message": (
                                "This email is already linked "
                                "to another Cognito identity."
                            ),
                            "action": (
                                "Administrator reconciliation required."
                            ),
                        },
                    )

                # Safe linking only when no other identity exists.
                if not existing_sub:
                    user.cognito_sub = principal.sub

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
            db.flush()

        # Do not allow a disabled database account to reactivate itself.
        if not user.active:
            raise HTTPException(
                status_code=403,
                detail="Your ThinkSmart account is disabled",
            )

        # Cognito is the authentication and role authority.
        user.role = principal.role

        # Update profile fields only when necessary.
        if user.email.lower() != email:
            user.email = email

        if full_name and full_name != "ThinkSmart user":
            user.full_name = full_name[:160]

        db.commit()
        db.refresh(user)

        return user

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        # Possible concurrent account creation or unique email conflict.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "USER_PROFILE_CONFLICT",
                "message": (
                    "The user profile could not be linked safely."
                ),
            },
        )

    except Exception:
        db.rollback()
        raise


def require_admin(
    principal: CognitoPrincipal = Depends(get_current_user),
) -> CognitoPrincipal:

    if not principal.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Administrator permission required",
        )

    return principal


def require_admin_user(
    principal: CognitoPrincipal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:

    return get_business_user(principal, db)


def require_lead_access(
    user: User,
    lead,
) -> None:

    if (
        user.role not in {
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
        }
        and lead.assigned_to != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="Lead not found",
        )
