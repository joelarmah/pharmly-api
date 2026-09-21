"""add ON DELETE CASCADE for User deletion

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-21

"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# (constraint name, table, column, referenced table)
_CASCADES = [
    ("refresh_tokens_user_id_fkey", "refresh_tokens", "user_id", "users"),
    ("prescriptions_user_id_fkey", "prescriptions", "user_id", "users"),
    ("medications_prescription_id_fkey", "medications", "prescription_id", "prescriptions"),
    ("orders_user_id_fkey", "orders", "user_id", "users"),
    ("orders_prescription_id_fkey", "orders", "prescription_id", "prescriptions"),
    ("payment_transactions_user_id_fkey", "payment_transactions", "user_id", "users"),
    ("payment_transactions_order_id_fkey", "payment_transactions", "order_id", "orders"),
]


def upgrade() -> None:
    for name, table, column, ref_table in _CASCADES:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref_table, [column], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    for name, table, column, ref_table in reversed(_CASCADES):
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref_table, [column], ["id"])
