"""Add authentication columns and refresh-session storage."""
from alembic import op

revision = "0001_authentication"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create any missing application tables on a fresh database; existing MVP tables are left intact.
    from app.core.database import Base
    from app.models import entities  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    # Idempotent for databases created by the original MVP's create_all().
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(500)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL")
    op.execute("""CREATE TABLE IF NOT EXISTS refresh_sessions (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(64) NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ NULL, user_agent VARCHAR(500) NULL, ip_address VARCHAR(64) NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_sessions_user_id ON refresh_sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_sessions_token_hash ON refresh_sessions(token_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_sessions_expires_at ON refresh_sessions(expires_at)")

def downgrade():
    op.execute("DROP TABLE IF EXISTS refresh_sessions")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locked_until")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_attempts")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS must_change_password")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
