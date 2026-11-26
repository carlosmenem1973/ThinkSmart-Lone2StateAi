"""Create centralized omnichannel communications schema."""
from alembic import op
import sqlalchemy as sa

revision = "0009_communications"
down_revision = "0008_usage_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "communication_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("account_scope", sa.String(20), nullable=False, server_default="central"),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("sender_identifier", sa.String(320), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("configuration_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel", "provider", "display_name", name="uq_communication_channel_provider_name"),
    )

    op.create_table(
        "contact_channel_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("lawful_basis", sa.String(80), nullable=True),
        sa.Column("evidence_source", sa.String(500), nullable=True),
        sa.Column("evidence_reference", sa.String(1000), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("contact_id", "channel", "purpose", name="uq_contact_channel_purpose_consent"),
    )
    op.create_index("ix_contact_channel_consents_contact_id", "contact_channel_consents", ["contact_id"])

    op.create_table(
        "communication_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("external_thread_id", sa.String(320), nullable=True),
        sa.Column("subject", sa.String(998), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_communication_threads_contact_id", "communication_threads", ["contact_id"])
    op.create_index("ix_communication_threads_lead_id", "communication_threads", ["lead_id"])
    op.create_index("ix_communication_threads_channel", "communication_threads", ["channel"])
    op.create_index("ix_communication_threads_external_thread_id", "communication_threads", ["external_thread_id"])
    op.create_index("ix_communication_threads_status", "communication_threads", ["status"])
    op.create_index("ix_communication_threads_last_message_at", "communication_threads", ["last_message_at"])
    op.create_index("ix_communication_threads_contact_channel", "communication_threads", ["contact_id", "channel"])

    op.create_table(
        "communication_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.Integer(), sa.ForeignKey("communication_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("provider_message_id", sa.String(320), nullable=True),
        sa.Column("reply_to_message_id", sa.Integer(), sa.ForeignKey("communication_messages.id"), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_message_id", name="uq_communication_provider_message"),
    )
    op.create_index("ix_communication_messages_thread_id", "communication_messages", ["thread_id"])
    op.create_index("ix_communication_messages_status", "communication_messages", ["status"])
    op.create_index("ix_communication_messages_thread_created", "communication_messages", ["thread_id", "created_at"])

    op.create_table(
        "communication_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("event_id", sa.String(320), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "event_id", name="uq_communication_provider_event"),
    )


def downgrade():
    op.drop_table("communication_webhook_events")
    op.drop_index("ix_communication_messages_thread_created", table_name="communication_messages")
    op.drop_index("ix_communication_messages_status", table_name="communication_messages")
    op.drop_index("ix_communication_messages_thread_id", table_name="communication_messages")
    op.drop_table("communication_messages")
    op.drop_index("ix_communication_threads_contact_channel", table_name="communication_threads")
    for name in ("last_message_at", "status", "external_thread_id", "channel", "lead_id", "contact_id"):
        op.drop_index(f"ix_communication_threads_{name}", table_name="communication_threads")
    op.drop_table("communication_threads")
    op.drop_index("ix_contact_channel_consents_contact_id", table_name="contact_channel_consents")
    op.drop_table("contact_channel_consents")
    op.drop_table("communication_channels")
