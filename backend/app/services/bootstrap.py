from sqlalchemy import select, text
from app.core.auth import hash_password
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User, UserRole

def ensure_bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        # Serialize first-admin creation when multiple ECS tasks start simultaneously.
        db.execute(text("SELECT pg_advisory_xact_lock(824731905)"))
        existing = db.scalar(select(User).where(User.role == UserRole.ADMIN).limit(1))
        if existing and existing.password_hash:
            return
        if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
            if settings.environment.lower() in {"prod", "production"}:
                raise RuntimeError("No usable administrator exists. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD for initial provisioning.")
            return
        bootstrap_password = settings.bootstrap_admin_password
        if len(bootstrap_password) < 16 or not any(c.islower() for c in bootstrap_password) or not any(c.isupper() for c in bootstrap_password) or not any(c.isdigit() for c in bootstrap_password):
            raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 16 characters and include upper-case, lower-case and numeric characters")
        email = settings.bootstrap_admin_email.strip().lower()
        user = existing or db.scalar(select(User).where(User.email == email))
        if user:
            user.role = UserRole.ADMIN
            user.active = True
            user.password_hash = hash_password(settings.bootstrap_admin_password)
            user.must_change_password = False
        else:
            user = User(email=email, full_name="EstateAI Administrator", role=UserRole.ADMIN, active=True, password_hash=hash_password(settings.bootstrap_admin_password), must_change_password=False)
            db.add(user)
        db.commit()
    finally:
        db.close()
