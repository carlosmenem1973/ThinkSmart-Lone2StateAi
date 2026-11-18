"""Add Cognito RBAC roles to the existing users role enum.

Revision ID: 0004_cognito_rbac
Revises: 0003_cognito_identity
"""
from alembic import op

revision = "0004_cognito_rbac"
down_revision = "0003_cognito_identity"
branch_labels = None
depends_on = None

def upgrade():
    # SQLAlchemy Enum(UserRole) uses the enum type name "userrole" and stores
    # Python enum member names by default (ADMIN, SELLER, ...).
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MANAGER'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'VIEWER'")

def downgrade():
    # PostgreSQL cannot safely remove enum labels while rows or prepared
    # statements may reference them. Keep labels; application rollback is code-only.
    pass
