"""Add authenticated application usage analytics."""
from alembic import op
import sqlalchemy as sa

revision = "0006_usage_analytics"
down_revision = "0005_contact_ai"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("route", sa.String(length=120), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_events_user_created", "usage_events", ["user_id", "created_at"])
    op.create_index("ix_usage_events_feature_created", "usage_events", ["feature", "created_at"])

def downgrade():
    op.drop_index("ix_usage_events_feature_created", table_name="usage_events")
    op.drop_index("ix_usage_events_user_created", table_name="usage_events")
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_table("usage_events")
