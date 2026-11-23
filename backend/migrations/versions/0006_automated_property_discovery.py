"""Add configurable scheduled property discovery to Contact AI settings."""
from alembic import op
import sqlalchemy as sa

revision = "0006_property_discovery"
down_revision = "0005_contact_ai"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contact_ai_settings", sa.Column("search_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("contact_ai_settings", sa.Column("search_query", sa.Text(), nullable=False, server_default="Oportunidades imobiliárias publicadas recentemente em Portugal"))
    op.add_column("contact_ai_settings", sa.Column("search_interval_minutes", sa.Integer(), nullable=False, server_default="1440"))
    op.add_column("contact_ai_settings", sa.Column("last_search_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contact_ai_settings", sa.Column("next_search_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("contact_ai_settings", "next_search_at")
    op.drop_column("contact_ai_settings", "last_search_at")
    op.drop_column("contact_ai_settings", "search_interval_minutes")
    op.drop_column("contact_ai_settings", "search_query")
    op.drop_column("contact_ai_settings", "search_enabled")
