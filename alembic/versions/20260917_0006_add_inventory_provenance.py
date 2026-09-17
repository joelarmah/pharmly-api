"""add inventory provenance to pharmacies and pharmacy prices

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17

"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pharmacies",
        sa.Column("inventory_source", sa.String(), nullable=True),
    )
    op.execute("UPDATE pharmacies SET inventory_source = 'manual'")
    op.alter_column("pharmacies", "inventory_source", nullable=False)

    op.add_column("pharmacy_prices", sa.Column("stock_quantity", sa.Integer(), nullable=True))
    op.add_column("pharmacy_prices", sa.Column("source", sa.String(), nullable=True))
    op.add_column("pharmacy_prices", sa.Column("synced_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE pharmacy_prices SET source = 'seed', synced_at = now()")
    op.alter_column("pharmacy_prices", "source", nullable=False)
    op.alter_column("pharmacy_prices", "synced_at", nullable=False)


def downgrade() -> None:
    op.drop_column("pharmacy_prices", "synced_at")
    op.drop_column("pharmacy_prices", "source")
    op.drop_column("pharmacy_prices", "stock_quantity")
    op.drop_column("pharmacies", "inventory_source")
