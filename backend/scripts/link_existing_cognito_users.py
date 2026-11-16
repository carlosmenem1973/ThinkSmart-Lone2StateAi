"""One-time explicit linking of existing DB users to existing Cognito users by verified email."""
import boto3
from sqlalchemy import select, func
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User

def main():
    client = boto3.client("cognito-idp", region_name=settings.aws_region)
    db = SessionLocal()
    linked = 0
    try:
        paginator = client.get_paginator("list_users")
        for page in paginator.paginate(UserPoolId=settings.cognito_user_pool_id):
            for cognito_user in page.get("Users", []):
                attrs = {item["Name"]: item["Value"] for item in cognito_user.get("Attributes", [])}
                email = attrs.get("email", "").strip().lower()
                sub = attrs.get("sub")
                if not email or not sub or attrs.get("email_verified", "false").lower() != "true":
                    continue
                app_user = db.scalar(select(User).where(func.lower(User.email) == email))
                if app_user and app_user.active and not app_user.cognito_sub:
                    app_user.cognito_sub = sub
                    linked += 1
        db.commit()
        print(f"Linked {linked} existing application users to Cognito identities.")
    finally:
        db.close()

if __name__ == "__main__":
    if not settings.cognito_user_pool_id: raise SystemExit("COGNITO_USER_POOL_ID is required")
    main()
