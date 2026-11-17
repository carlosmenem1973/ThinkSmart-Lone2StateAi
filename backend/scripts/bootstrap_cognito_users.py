
"""Safely provision selected existing Cognito identities into ThinkSmart."""
import argparse

import boto3
from sqlalchemy import select, func

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User, UserRole


TARGET_USERS = {
    "management@thinksmart.pt": UserRole.ADMIN,
    "info@thinksmart.pt": UserRole.SELLER,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag, only performs a dry run.",
    )
    args = parser.parse_args()

    client = boto3.client("cognito-idp", region_name=settings.aws_region)
    db = SessionLocal()

    found = {}
    created = 0
    skipped = 0

    try:
        paginator = client.get_paginator("list_users")

        for page in paginator.paginate(
            UserPoolId=settings.cognito_user_pool_id
        ):
            for cognito_user in page.get("Users", []):
                attrs = {
                    item["Name"]: item["Value"]
                    for item in cognito_user.get("Attributes", [])
                }

                email = attrs.get("email", "").strip().lower()

                if email not in TARGET_USERS:
                    continue

                found[email] = cognito_user

        for email, role in TARGET_USERS.items():
            cognito_user = found.get(email)

            if not cognito_user:
                print(f"NOT_FOUND: {email}")
                skipped += 1
                continue

            attrs = {
                item["Name"]: item["Value"]
                for item in cognito_user.get("Attributes", [])
            }

            sub = attrs.get("sub")
            verified = attrs.get("email_verified", "false").lower() == "true"
            enabled = cognito_user.get("Enabled", False)

            if not sub or not verified or not enabled:
                print(
                    f"SKIPPED: {email} "
                    f"(verified={verified}, enabled={enabled})"
                )
                skipped += 1
                continue

            existing = db.scalars(
                select(User).where(
                    func.lower(User.email) == email
                )
            ).all()

            if existing:
                print(f"EXISTS: {email} - no changes made")
                skipped += 1
                continue

            subject_owner = db.scalar(
                select(User).where(User.cognito_sub == sub)
            )

            if subject_owner:
                print(f"CONFLICT: Cognito identity already linked")
                skipped += 1
                continue

            full_name = attrs.get("name") or email.split("@")[0]

            user = User(
                email=email,
                cognito_sub=sub,
                full_name=full_name,
                role=role,
                territory=None,
                active=True,
                password_hash=None,
                must_change_password=False,
            )

            db.add(user)
            created += 1

            print(f"READY: {email} role={role.value}")

        if args.apply:
            db.commit()
            print("DATABASE CHANGES COMMITTED")
        else:
            db.rollback()
            print("DRY RUN: no database changes made")

        print(f"Created: {created}")
        print(f"Skipped: {skipped}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if not settings.cognito_user_pool_id:
        raise SystemExit("COGNITO_USER_POOL_ID is required")

    main()
