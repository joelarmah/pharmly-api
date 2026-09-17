"""add unique constraint on pharmacies name

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17

"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_pharmacies_name", "pharmacies", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_pharmacies_name", "pharmacies", type_="unique")
