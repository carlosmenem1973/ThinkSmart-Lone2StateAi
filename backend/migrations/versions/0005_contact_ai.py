"""Add website Contact AI settings and conversations."""
from alembic import op
import sqlalchemy as sa

revision = "0005_contact_ai"
down_revision = "0004_cognito_rbac"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "contact_ai_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="approval"),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="website"),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "contact_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("visitor_id", sa.String(length=80), nullable=False),
        sa.Column("visitor_name", sa.String(length=160), nullable=True),
        sa.Column("visitor_email", sa.String(length=320), nullable=True),
        sa.Column("consent_to_followup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_contact_conversations_visitor_id", "contact_conversations", ["visitor_id"])
    op.create_index("ix_contact_conversations_status", "contact_conversations", ["status"])
    op.create_index("ix_contact_conversations_last_message_at", "contact_conversations", ["last_message_at"])
    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("contact_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_contact_messages_conversation_id", "contact_messages", ["conversation_id"])

def downgrade():
    op.drop_index("ix_contact_messages_conversation_id", table_name="contact_messages")
    op.drop_table("contact_messages")
    op.drop_index("ix_contact_conversations_last_message_at", table_name="contact_conversations")
    op.drop_index("ix_contact_conversations_status", table_name="contact_conversations")
    op.drop_index("ix_contact_conversations_visitor_id", table_name="contact_conversations")
    op.drop_table("contact_conversations")
    op.drop_table("contact_ai_settings")
