"""add phone_lookup_attempts table

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-22

"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_lookup_attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_phone_lookup_attempts_phone_number",
        "phone_lookup_attempts",
        ["phone_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("phone_lookup_attempts")
