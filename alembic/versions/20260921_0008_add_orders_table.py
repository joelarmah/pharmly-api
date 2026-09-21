"""add orders table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-21

"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("prescription_id", sa.String(), nullable=False),
        sa.Column("pharmacy_id", sa.String(), nullable=False),
        sa.Column("payment_type", sa.String(), nullable=False),
        sa.Column("payment_reference", sa.String(), nullable=True),
        sa.Column("progress", sa.String(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("placed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_pharmacy_id", "orders", ["pharmacy_id"], unique=False)
    op.create_index("ix_orders_prescription_id", "orders", ["prescription_id"], unique=True)
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_index("ix_orders_prescription_id", table_name="orders")
    op.drop_index("ix_orders_pharmacy_id", table_name="orders")
    op.drop_table("orders")
