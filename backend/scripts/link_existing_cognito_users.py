"""Diagnose Cognito-to-application user matching without modifying the database."""
import boto3
from sqlalchemy import func, select
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User


def main():
    client = boto3.client("cognito-idp", region_name=settings.aws_region)
    db = SessionLocal()

    counts = {
        "cognito_total": 0,
        "email_unverified": 0,
        "missing_email_or_sub": 0,
        "no_application_user": 0,
        "inactive_application_user": 0,
        "already_linked": 0,
        "ready_to_link": 0,
        "duplicate_application_email": 0,
        "cognito_sub_conflict": 0,
    }

    try:
        paginator = client.get_paginator("list_users")

        for page in paginator.paginate(
            UserPoolId=settings.cognito_user_pool_id
        ):
            for cognito_user in page.get("Users", []):
                counts["cognito_total"] += 1

                attrs = {
                    item["Name"]: item["Value"]
                    for item in cognito_user.get("Attributes", [])
                }

                email = attrs.get("email", "").strip().lower()
                sub = attrs.get("sub")

                if not email or not sub:
                    counts["missing_email_or_sub"] += 1
                    continue

                if attrs.get("email_verified", "false").lower() != "true":
                    counts["email_unverified"] += 1
                    continue

                matches = db.scalars(
                    select(User).where(func.lower(User.email) == email)
                ).all()

                if not matches:
                    counts["no_application_user"] += 1
                    continue

                if len(matches) > 1:
                    counts["duplicate_application_email"] += 1
                    continue

                app_user = matches[0]

                if not app_user.active:
                    counts["inactive_application_user"] += 1
                    continue

                if app_user.cognito_sub == sub:
                    counts["already_linked"] += 1
                    continue

                if app_user.cognito_sub:
                    counts["cognito_sub_conflict"] += 1
                    continue

                existing = db.scalar(
                    select(User).where(User.cognito_sub == sub)
                )

                if existing:
                    counts["cognito_sub_conflict"] += 1
                    continue

                counts["ready_to_link"] += 1

        for key, value in counts.items():
            print(f"{key}: {value}")

    finally:
        db.close()


if __name__ == "__main__":
    if not settings.cognito_user_pool_id:
        raise SystemExit("COGNITO_USER_POOL_ID is required")
    main()
