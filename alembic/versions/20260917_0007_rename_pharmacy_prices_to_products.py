"""rename pharmacy_prices to pharmacy_products

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-17

"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("pharmacy_prices", "pharmacy_products")
    op.execute("ALTER INDEX pharmacy_prices_pkey RENAME TO pharmacy_products_pkey")
    op.execute(
        "ALTER INDEX ix_pharmacy_prices_pharmacy_id RENAME TO ix_pharmacy_products_pharmacy_id"
    )
    op.execute(
        "ALTER INDEX ix_pharmacy_prices_catalog_id RENAME TO ix_pharmacy_products_catalog_id"
    )
    op.execute(
        "ALTER TABLE pharmacy_products RENAME CONSTRAINT pharmacy_prices_pharmacy_id_fkey "
        "TO pharmacy_products_pharmacy_id_fkey"
    )
    op.execute(
        "ALTER TABLE pharmacy_products RENAME CONSTRAINT pharmacy_prices_catalog_id_fkey "
        "TO pharmacy_products_catalog_id_fkey"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE pharmacy_products RENAME CONSTRAINT pharmacy_products_catalog_id_fkey "
        "TO pharmacy_prices_catalog_id_fkey"
    )
    op.execute(
        "ALTER TABLE pharmacy_products RENAME CONSTRAINT pharmacy_products_pharmacy_id_fkey "
        "TO pharmacy_prices_pharmacy_id_fkey"
    )
    op.execute(
        "ALTER INDEX ix_pharmacy_products_catalog_id RENAME TO ix_pharmacy_prices_catalog_id"
    )
    op.execute(
        "ALTER INDEX ix_pharmacy_products_pharmacy_id RENAME TO ix_pharmacy_prices_pharmacy_id"
    )
    op.execute("ALTER INDEX pharmacy_products_pkey RENAME TO pharmacy_prices_pkey")
    op.rename_table("pharmacy_products", "pharmacy_prices")
