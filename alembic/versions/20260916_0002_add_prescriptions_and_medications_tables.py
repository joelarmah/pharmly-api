"""add prescriptions and medications tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16

"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('prescriptions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prescriptions_user_id'), 'prescriptions', ['user_id'], unique=False)
    op.create_table('medications',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('prescription_id', sa.String(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('dosage', sa.String(), nullable=False),
    sa.Column('dosage_unit', sa.String(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('quantity_unit', sa.String(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('dose_amount', sa.Integer(), nullable=False),
    sa.Column('duration_days', sa.Integer(), nullable=False),
    sa.Column('reminder_enabled', sa.Boolean(), nullable=False),
    sa.Column('notification_days', sa.JSON(), nullable=False),
    sa.Column('frequency', sa.String(), nullable=False),
    sa.Column('times', sa.JSON(), nullable=False),
    sa.Column('start_from', sa.String(), nullable=False),
    sa.Column('end_on', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['prescription_id'], ['prescriptions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_medications_prescription_id'), 'medications', ['prescription_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_medications_prescription_id'), table_name='medications')
    op.drop_table('medications')
    op.drop_index(op.f('ix_prescriptions_user_id'), table_name='prescriptions')
    op.drop_table('prescriptions')
