"""Add durable transactional outbox for outbound communications."""
from alembic import op
import sqlalchemy as sa

revision = "0010_communications_outbox"
down_revision = "0009_communications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "communication_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("communication_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_communication_outbox_status", "communication_outbox", ["status"])
    op.create_index("ix_communication_outbox_available_at", "communication_outbox", ["available_at"])


def downgrade():
    op.drop_index("ix_communication_outbox_available_at", table_name="communication_outbox")
    op.drop_index("ix_communication_outbox_status", table_name="communication_outbox")
    op.drop_table("communication_outbox")
