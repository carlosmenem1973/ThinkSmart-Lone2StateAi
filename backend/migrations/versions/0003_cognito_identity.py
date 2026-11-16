"""Link application users to existing Cognito identities."""
from alembic import op
import sqlalchemy as sa

revision = "0003_cognito_identity"
down_revision = "0002_brand_settings"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("cognito_sub", sa.String(length=128), nullable=True))
    op.create_index("ix_users_cognito_sub", "users", ["cognito_sub"], unique=True)

def downgrade():
    op.drop_index("ix_users_cognito_sub", table_name="users")
    op.drop_column("users", "cognito_sub")
