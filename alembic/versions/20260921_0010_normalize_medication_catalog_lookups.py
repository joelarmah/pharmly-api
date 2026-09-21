"""normalize medication_catalog type/form/unit into lookup tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21

"""

import sqlalchemy as sa

from alembic import op
from app.core.ids import generate_id

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_LOOKUPS = {
    "medication_types": "type",
    "medication_forms": "form",
    "dosage_units": "unit",
}


def upgrade() -> None:
    for table in _LOOKUPS:
        op.create_table(
            table,
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name=f"uq_{table}_name"),
        )

    bind = op.get_bind()

    id_by_value: dict[str, dict[str, str]] = {}
    for table, column in _LOOKUPS.items():
        id_by_value[column] = {}
        rows = bind.execute(sa.text(f"SELECT DISTINCT {column} FROM medication_catalog"))
        for (value,) in rows:
            row_id = generate_id()
            bind.execute(
                sa.text(f"INSERT INTO {table} (id, name) VALUES (:id, :name)"),
                {"id": row_id, "name": value},
            )
            id_by_value[column][value] = row_id

    op.add_column("medication_catalog", sa.Column("type_id", sa.String(), nullable=True))
    op.add_column("medication_catalog", sa.Column("form_id", sa.String(), nullable=True))
    op.add_column("medication_catalog", sa.Column("unit_id", sa.String(), nullable=True))

    for column in _LOOKUPS.values():
        for value, row_id in id_by_value[column].items():
            bind.execute(
                sa.text(
                    f"UPDATE medication_catalog SET {column}_id = :rid WHERE {column} = :val"
                ),
                {"rid": row_id, "val": value},
            )

    op.alter_column("medication_catalog", "type_id", nullable=False)
    op.alter_column("medication_catalog", "form_id", nullable=False)
    op.alter_column("medication_catalog", "unit_id", nullable=False)

    op.drop_constraint(
        "uq_medication_catalog_name_dosage_unit", "medication_catalog", type_="unique"
    )
    op.drop_column("medication_catalog", "type")
    op.drop_column("medication_catalog", "form")
    op.drop_column("medication_catalog", "unit")

    op.create_foreign_key(
        "medication_catalog_type_id_fkey",
        "medication_catalog",
        "medication_types",
        ["type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "medication_catalog_form_id_fkey",
        "medication_catalog",
        "medication_forms",
        ["form_id"],
        ["id"],
    )
    op.create_foreign_key(
        "medication_catalog_unit_id_fkey",
        "medication_catalog",
        "dosage_units",
        ["unit_id"],
        ["id"],
    )
    op.create_index("ix_medication_catalog_type_id", "medication_catalog", ["type_id"])
    op.create_index("ix_medication_catalog_form_id", "medication_catalog", ["form_id"])
    op.create_index("ix_medication_catalog_unit_id", "medication_catalog", ["unit_id"])
    op.create_unique_constraint(
        "uq_medication_catalog_name_dosage_unit",
        "medication_catalog",
        ["name", "dosage", "unit_id"],
    )


def downgrade() -> None:
    op.add_column("medication_catalog", sa.Column("type", sa.String(), nullable=True))
    op.add_column("medication_catalog", sa.Column("form", sa.String(), nullable=True))
    op.add_column("medication_catalog", sa.Column("unit", sa.String(), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE medication_catalog mc SET type = mt.name "
            "FROM medication_types mt WHERE mt.id = mc.type_id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE medication_catalog mc SET form = mf.name "
            "FROM medication_forms mf WHERE mf.id = mc.form_id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE medication_catalog mc SET unit = du.name "
            "FROM dosage_units du WHERE du.id = mc.unit_id"
        )
    )

    op.alter_column("medication_catalog", "type", nullable=False)
    op.alter_column("medication_catalog", "form", nullable=False)
    op.alter_column("medication_catalog", "unit", nullable=False)

    op.drop_constraint(
        "uq_medication_catalog_name_dosage_unit", "medication_catalog", type_="unique"
    )
    op.drop_index("ix_medication_catalog_type_id", table_name="medication_catalog")
    op.drop_index("ix_medication_catalog_form_id", table_name="medication_catalog")
    op.drop_index("ix_medication_catalog_unit_id", table_name="medication_catalog")
    op.drop_constraint(
        "medication_catalog_type_id_fkey", "medication_catalog", type_="foreignkey"
    )
    op.drop_constraint(
        "medication_catalog_form_id_fkey", "medication_catalog", type_="foreignkey"
    )
    op.drop_constraint(
        "medication_catalog_unit_id_fkey", "medication_catalog", type_="foreignkey"
    )
    op.drop_column("medication_catalog", "type_id")
    op.drop_column("medication_catalog", "form_id")
    op.drop_column("medication_catalog", "unit_id")

    op.create_unique_constraint(
        "uq_medication_catalog_name_dosage_unit", "medication_catalog", ["name", "dosage", "unit"]
    )

    op.drop_table("dosage_units")
    op.drop_table("medication_forms")
    op.drop_table("medication_types")
