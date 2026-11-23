"""Add central owners and clients directory."""
from alembic import op
import sqlalchemy as sa

revision = "0007_contacts_directory"
down_revision = "0006_property_discovery"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_type", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("municipality", sa.String(length=120), nullable=True),
        sa.Column("district", sa.String(length=120), nullable=True),
        sa.Column("property_preferences", sa.Text(), nullable=True),
        sa.Column("budget_min", sa.Integer(), nullable=True),
        sa.Column("budget_max", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lawful_basis", sa.String(length=500), nullable=True),
        sa.Column("contact_permission", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_contacts_contact_type", "contacts", ["contact_type"])
    op.create_index("ix_contacts_full_name", "contacts", ["full_name"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_municipality", "contacts", ["municipality"])
    op.create_index("ix_contacts_assigned_to", "contacts", ["assigned_to"])
    op.create_index("ix_contacts_type_active", "contacts", ["contact_type", "active"])

def downgrade():
    op.drop_table("contacts")
