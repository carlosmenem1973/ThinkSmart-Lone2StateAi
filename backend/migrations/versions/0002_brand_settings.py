"""Add editable workspace branding settings."""
from alembic import op

revision = "0002_brand_settings"
down_revision = "0001_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS brand_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            product_name VARCHAR(100) NOT NULL DEFAULT 'ThinkSmart AI',
            customer_name VARCHAR(160) NOT NULL DEFAULT 'Loft2 Real Estate',
            tagline VARCHAR(240) NOT NULL DEFAULT 'Real Estate Intelligence',
            logo_url VARCHAR(1000) NULL,
            primary_color VARCHAR(7) NOT NULL DEFAULT '#2563EB',
            accent_color VARCHAR(7) NOT NULL DEFAULT '#16866C',
            updated_by INTEGER NULL REFERENCES users(id),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        INSERT INTO brand_settings (
            id,
            product_name,
            customer_name,
            tagline,
            primary_color,
            accent_color,
            updated_at
        )
        VALUES (
            1,
            'ThinkSmart AI',
            'Loft2 Real Estate',
            'Real Estate Intelligence',
            '#2563EB',
            '#16866C',
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS brand_settings")
