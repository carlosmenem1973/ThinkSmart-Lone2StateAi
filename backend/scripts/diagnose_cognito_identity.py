
from __future__ import annotations

import hashlib
import json
import logging
import sys
from collections import Counter, defaultdict
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("cognito-identity-diagnostic")


def fingerprint(value: str | None) -> str | None:
    """Return a short SHA-256 fingerprint without exposing the original value."""
    if not value:
        return None

    normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def emit(event: str, **data: Any) -> None:
    """Print structured JSON suitable for CloudWatch Logs."""
    print(
        json.dumps(
            {"event": event, **data},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def get_cognito_users(client: Any) -> list[dict[str, str | None]]:
    """Retrieve Cognito users using pagination; never print personal data."""
    users: list[dict[str, str | None]] = []
    pagination_token: str | None = None

    while True:
        arguments: dict[str, Any] = {
            "UserPoolId": settings.cognito_user_pool_id,
            "Limit": 60,
        }

        if pagination_token:
            arguments["PaginationToken"] = pagination_token

        response = client.list_users(**arguments)

        for cognito_user in response.get("Users", []):
            attributes = {
                item["Name"]: item["Value"]
                for item in cognito_user.get("Attributes", [])
            }

            users.append(
                {
                    "username": cognito_user.get("Username"),
                    "sub": attributes.get("sub"),
                    "email": attributes.get("email"),
                }
            )

        pagination_token = response.get("PaginationToken")

        if not pagination_token:
            break

    return users


def diagnose_users(
    database_users: list[User],
    cognito_users: list[dict[str, str | None]],
) -> list[dict[str, Any]]:
    """Compare database identities with Cognito identities without modifying data."""

    cognito_by_email: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    cognito_by_sub: dict[str, dict[str, str | None]] = {}

    for cognito_user in cognito_users:
        email = cognito_user.get("email")
        sub = cognito_user.get("sub")

        if email:
            cognito_by_email[email.strip().lower()].append(cognito_user)

        if sub:
            cognito_by_sub[sub] = cognito_user

    results: list[dict[str, Any]] = []

    for user in database_users:
        email = (user.email or "").strip().lower()
        db_sub = user.cognito_sub

        email_matches = cognito_by_email.get(email, [])
        old_identity = cognito_by_sub.get(db_sub) if db_sub else None

        if len(email_matches) > 1:
            status = "MULTIPLE_COGNITO_EMAIL_MATCHES"

        elif len(email_matches) == 1:
            cognito_sub = email_matches[0].get("sub")

            if not db_sub:
                status = "EMAIL_MATCH_WITHOUT_DB_SUB"
            elif db_sub == cognito_sub:
                status = "IDENTITY_MATCH"
            else:
                status = "EMAIL_MATCH_SUB_CONFLICT"

        elif old_identity:
            status = "DB_SUB_FOUND_WITH_DIFFERENT_EMAIL"

        elif db_sub:
            status = "DB_SUB_NOT_FOUND_IN_COGNITO"

        else:
            status = "NO_COGNITO_IDENTITY_MATCH"

        results.append(
            {
                "user_id": user.id,
                "email_fingerprint": fingerprint(email),
                "db_sub_fingerprint": fingerprint(db_sub),
                "db_sub_exists_in_cognito": old_identity is not None,
                "db_sub_email_fingerprint": fingerprint(
                    old_identity.get("email") if old_identity else None
                ),
                "cognito_email_match_count": len(email_matches),
                "matching_cognito_sub_fingerprints": [
                    fingerprint(item.get("sub"))
                    for item in email_matches
                ],
                "active": user.active,
                "role": user.role.value if user.role else None,
                "status": status,
            }
        )

    return results


def main() -> int:
    if not settings.database_url:
        emit("configuration_error", detail="DATABASE_URL is not configured")
        return 1

    if not settings.cognito_user_pool_id:
        emit(
            "configuration_error",
            detail="COGNITO_USER_POOL_ID is not configured",
        )
        return 1

    db = None

    try:
        logger.info("Starting read-only identity diagnostic")

        db = SessionLocal()

        database_users = list(
            db.scalars(
                select(User).order_by(User.id)
            ).all()
        )

        logger.info("Database connection successful")

        cognito = boto3.client(
            "cognito-idp",
            region_name=settings.aws_region,
        )

        cognito_users = get_cognito_users(cognito)

        logger.info("Cognito ListUsers completed successfully")

        results = diagnose_users(database_users, cognito_users)

        duplicate_email_counts = Counter(
            (user.email or "").strip().lower()
            for user in database_users
        )

        duplicate_emails = sum(
            1 for count in duplicate_email_counts.values() if count > 1
        )

        status_counts = Counter(
            result["status"] for result in results
        )

        emit(
            "diagnostic_summary",
            database_user_count=len(database_users),
            cognito_user_count=len(cognito_users),
            case_insensitive_duplicate_email_groups=duplicate_emails,
            status_counts=dict(status_counts),
            read_only=True,
        )

        for result in results:
            emit("user_identity_result", **result)

        emit(
            "diagnostic_completed",
            success=True,
            database_checked=True,
            cognito_checked=True,
            records_checked=len(results),
            changes_made=0,
        )

        return 0

    except ClientError as exc:
        error = exc.response.get("Error", {})
        emit(
            "aws_error",
            error_code=error.get("Code"),
            detail="Cognito request failed; check ECS task IAM permissions",
        )
        return 1

    except BotoCoreError:
        emit(
            "aws_connection_error",
            detail="Unable to communicate with AWS Cognito",
        )
        return 1

    except Exception as exc:
        logger.exception("Identity diagnostic failed")
        emit(
            "diagnostic_error",
            error_type=type(exc).__name__,
            detail=str(exc)[:500],
        )
        return 1

    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
