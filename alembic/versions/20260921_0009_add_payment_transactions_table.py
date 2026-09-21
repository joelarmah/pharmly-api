"""add payment transactions table

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-21

"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("paystack_raw_response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_transactions_order_id", "payment_transactions", ["order_id"], unique=False
    )
    op.create_index(
        "ix_payment_transactions_reference", "payment_transactions", ["reference"], unique=True
    )
    op.create_index(
        "ix_payment_transactions_user_id", "payment_transactions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_payment_transactions_user_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_reference", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_order_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")
