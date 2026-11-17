
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.entities import User

db = SessionLocal()

try:
    users = db.scalars(select(User)).all()

    print(f"Application users: {len(users)}")

    for user in users:
        email = user.email or ""
        masked = email[:2] + "***" + email[email.find("@"):] if "@" in email else "***"

        print({
            "email": masked,
            "active": user.active,
            "has_cognito_sub": bool(user.cognito_sub),
            "role": str(user.role),
        })
finally:
    db.close()
