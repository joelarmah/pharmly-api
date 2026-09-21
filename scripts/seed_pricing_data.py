"""Seeds medication_catalog, pharmacies, and pharmacy_products.

pharmacy_products are entirely synthetic (a deterministic price per
pharmacy/catalog-entry pair) -- there is no real partner pricing data yet
(PRD §9 open question #4). This exists purely so v1 pricing has something
real to compute against; replace with a real import once partner data
exists.

Idempotent: safe to re-run. Existing rows are left untouched.

Usage:
    python -m scripts.seed_pricing_data
"""

import asyncio
import json
import random
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.pharmacy import (
    DosageUnit,
    MedicationCatalog,
    MedicationForm,
    MedicationType,
    Pharmacy,
    PharmacyProduct,
)

SEED_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "seed_data"

_BASE_PRICE_BY_TYPE = {
    "pills": 1.5,
    "injection": 15.0,
    "liquid": 8.0,
    "topical": 12.0,
    "drops": 10.0,
    "suppository": 6.0,
    "inhaler": 25.0,
    "powder": 7.0,
    "other": 5.0,
}


def _synthetic_unit_price(pharmacy_id: str, catalog_entry: MedicationCatalog) -> float:
    rng = random.Random(f"{pharmacy_id}:{catalog_entry.id}")
    base = _BASE_PRICE_BY_TYPE.get(catalog_entry.type.name, 5.0)
    return round(base * rng.uniform(0.85, 1.25), 2)


async def _get_or_create(db: AsyncSession, model: type, cache: dict, name: str):
    key = name.lower()
    if key in cache:
        return cache[key]

    existing = (await db.execute(select(model).where(model.name == name))).scalar_one_or_none()
    if existing is not None:
        cache[key] = existing
        return existing

    row = model(name=name)
    db.add(row)
    await db.flush()  # populate row.id via its Python-side default
    cache[key] = row
    return row


async def _seed_catalog(db: AsyncSession) -> list[MedicationCatalog]:
    entries = json.loads((SEED_DATA_DIR / "nhis_medications.json").read_text())

    existing = (
        (await db.execute(select(MedicationCatalog).options(selectinload(MedicationCatalog.unit))))
        .scalars()
        .all()
    )
    existing_keys = {(e.name.lower(), e.dosage, e.unit.name.lower()) for e in existing}

    types: dict[str, MedicationType] = {}
    forms: dict[str, MedicationForm] = {}
    units: dict[str, DosageUnit] = {}

    added = 0
    for entry in entries:
        key = (entry["name"].lower(), entry["dosage"], entry["unit"].lower())
        if key in existing_keys:
            continue
        type_row = await _get_or_create(db, MedicationType, types, entry["type"])
        form_row = await _get_or_create(db, MedicationForm, forms, entry["form"])
        unit_row = await _get_or_create(db, DosageUnit, units, entry["unit"])
        db.add(
            MedicationCatalog(
                name=entry["name"],
                dosage=entry["dosage"],
                unit_id=unit_row.id,
                form_id=form_row.id,
                type_id=type_row.id,
            )
        )
        existing_keys.add(key)
        added += 1

    await db.commit()
    print(f"medication_catalog: {added} added, {len(existing)} already present")
    return (
        (
            await db.execute(
                select(MedicationCatalog).options(
                    selectinload(MedicationCatalog.type),
                    selectinload(MedicationCatalog.form),
                    selectinload(MedicationCatalog.unit),
                )
            )
        )
        .scalars()
        .all()
    )


async def _seed_pharmacies(db: AsyncSession) -> list[Pharmacy]:
    entries = json.loads((SEED_DATA_DIR / "pharmacies.json").read_text())

    existing = (await db.execute(select(Pharmacy))).scalars().all()
    existing_names = {p.name for p in existing}

    added = 0
    for entry in entries:
        if entry["name"] in existing_names:
            continue
        db.add(
            Pharmacy(
                name=entry["name"],
                latitude=entry["latitude"],
                longitude=entry["longitude"],
                rating=entry.get("rating"),
            )
        )
        existing_names.add(entry["name"])
        added += 1

    await db.commit()
    print(f"pharmacies: {added} added, {len(existing)} already present")
    return (await db.execute(select(Pharmacy))).scalars().all()


async def _seed_prices(
    db: AsyncSession, pharmacies: list[Pharmacy], catalog: list[MedicationCatalog]
) -> None:
    existing = {
        (p.pharmacy_id, p.catalog_id)
        for p in (await db.execute(select(PharmacyProduct))).scalars().all()
    }

    added = 0
    for pharmacy in pharmacies:
        for entry in catalog:
            if (pharmacy.id, entry.id) in existing:
                continue
            db.add(
                PharmacyProduct(
                    pharmacy_id=pharmacy.id,
                    catalog_id=entry.id,
                    unit_price=_synthetic_unit_price(pharmacy.id, entry),
                    source="seed",
                )
            )
            added += 1

    await db.commit()
    print(f"pharmacy_products: {added} added, {len(existing)} already present")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        catalog = await _seed_catalog(db)
        pharmacies = await _seed_pharmacies(db)
        await _seed_prices(db, pharmacies, catalog)


if __name__ == "__main__":
    asyncio.run(main())
