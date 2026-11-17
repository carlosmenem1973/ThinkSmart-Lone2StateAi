"""Link application users to existing Cognito identities."""
from alembic import op

revision = "0003_cognito_identity"
down_revision = "0002_brand_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(128)
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_cognito_sub
        ON users (cognito_sub)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_users_cognito_sub")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cognito_sub")