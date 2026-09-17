"""add pharmacy pricing tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17

"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('medication_catalog',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('dosage', sa.String(), nullable=False),
    sa.Column('unit', sa.String(), nullable=False),
    sa.Column('form', sa.String(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('retired_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'dosage', 'unit', name='uq_medication_catalog_name_dosage_unit')
    )
    op.create_index(
        op.f('ix_medication_catalog_name'), 'medication_catalog', ['name'], unique=False
    )
    op.create_table('pharmacies',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pharmacy_prices',
    sa.Column('pharmacy_id', sa.String(), nullable=False),
    sa.Column('catalog_id', sa.String(), nullable=False),
    sa.Column('unit_price', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['catalog_id'], ['medication_catalog.id'], ),
    sa.ForeignKeyConstraint(['pharmacy_id'], ['pharmacies.id'], ),
    sa.PrimaryKeyConstraint('pharmacy_id', 'catalog_id')
    )
    op.create_index(
        op.f('ix_pharmacy_prices_catalog_id'), 'pharmacy_prices', ['catalog_id'], unique=False
    )
    op.create_index(
        op.f('ix_pharmacy_prices_pharmacy_id'), 'pharmacy_prices', ['pharmacy_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_pharmacy_prices_pharmacy_id'), table_name='pharmacy_prices')
    op.drop_index(op.f('ix_pharmacy_prices_catalog_id'), table_name='pharmacy_prices')
    op.drop_table('pharmacy_prices')
    op.drop_table('pharmacies')
    op.drop_index(op.f('ix_medication_catalog_name'), table_name='medication_catalog')
    op.drop_table('medication_catalog')
