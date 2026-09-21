from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApiError
from app.core.geo import estimate_eta_minutes, haversine_km
from app.models.pharmacy import DosageUnit, MedicationCatalog, Pharmacy, PharmacyProduct
from app.models.prescription import Medication, Prescription
from app.schemas.pricing import MedicationLineOfferOut, MedicationPricingLineOut, PharmacyOfferOut

CURRENCY = "GHS"


async def _load_owned_prescription(
    db: AsyncSession, user_id: str, prescription_id: str
) -> Prescription:
    result = await db.execute(
        select(Prescription)
        .where(Prescription.id == prescription_id, Prescription.user_id == user_id)
        .options(selectinload(Prescription.medications))
    )
    prescription = result.scalar_one_or_none()
    if prescription is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Prescription not found.")
    return prescription


async def _match_catalog(db: AsyncSession, medication: Medication) -> MedicationCatalog | None:
    name = medication.name.strip().lower()
    unit = medication.dosage_unit.strip().lower()
    dosage = medication.dosage.strip()

    result = await db.execute(
        select(MedicationCatalog)
        .join(DosageUnit, DosageUnit.id == MedicationCatalog.unit_id)
        .where(
            func.lower(MedicationCatalog.name) == name,
            MedicationCatalog.dosage == dosage,
            func.lower(DosageUnit.name) == unit,
            MedicationCatalog.retired_at.is_(None),
        )
    )
    return result.scalars().first()


def _distance_and_eta(
    lat: float | None, lon: float | None, pharmacy: Pharmacy
) -> tuple[float | None, int | None]:
    if lat is None or lon is None:
        return None, None
    distance_km = haversine_km(lat, lon, pharmacy.latitude, pharmacy.longitude)
    return round(distance_km, 2), estimate_eta_minutes(distance_km)


async def price_bundle(
    db: AsyncSession,
    user_id: str,
    prescription_id: str,
    latitude: float | None,
    longitude: float | None,
) -> list[PharmacyOfferOut]:
    prescription = await _load_owned_prescription(db, user_id, prescription_id)
    medications = prescription.medications

    catalog_by_medication_id = {med.id: await _match_catalog(db, med) for med in medications}
    matched_catalog_ids = [c.id for c in catalog_by_medication_id.values() if c is not None]
    if not matched_catalog_ids:
        return []

    pharmacies = (await db.execute(select(Pharmacy))).scalars().all()
    prices = (
        (
            await db.execute(
                select(PharmacyProduct).where(PharmacyProduct.catalog_id.in_(matched_catalog_ids))
            )
        )
        .scalars()
        .all()
    )
    price_by_key = {(p.pharmacy_id, p.catalog_id): p.unit_price for p in prices}

    offers = []
    for pharmacy in pharmacies:
        total = 0.0
        matched_count = 0
        for med in medications:
            catalog = catalog_by_medication_id[med.id]
            if catalog is None:
                continue
            unit_price = price_by_key.get((pharmacy.id, catalog.id))
            if unit_price is None:
                continue
            total += med.quantity * unit_price
            matched_count += 1

        if matched_count == 0:
            continue

        distance_km, eta_minutes = _distance_and_eta(latitude, longitude, pharmacy)
        offers.append(
            PharmacyOfferOut(
                pharmacy_id=pharmacy.id,
                pharmacy_name=pharmacy.name,
                total_price=round(total, 2),
                currency=CURRENCY,
                is_fully_in_stock=matched_count == len(medications),
                rating=pharmacy.rating,
                distance_km=distance_km,
                eta_minutes=eta_minutes,
            )
        )

    offers.sort(key=lambda offer: offer.total_price)
    return offers


async def price_per_medication(
    db: AsyncSession,
    user_id: str,
    prescription_id: str,
    latitude: float | None,
    longitude: float | None,
) -> list[MedicationPricingLineOut]:
    prescription = await _load_owned_prescription(db, user_id, prescription_id)

    lines = []
    for med in prescription.medications:
        catalog = await _match_catalog(db, med)
        offers: list[MedicationLineOfferOut] = []

        if catalog is not None:
            result = await db.execute(
                select(PharmacyProduct, Pharmacy)
                .join(Pharmacy, Pharmacy.id == PharmacyProduct.pharmacy_id)
                .where(PharmacyProduct.catalog_id == catalog.id)
            )
            for price, pharmacy in result.all():
                distance_km, eta_minutes = _distance_and_eta(latitude, longitude, pharmacy)
                offers.append(
                    MedicationLineOfferOut(
                        pharmacy_id=pharmacy.id,
                        pharmacy_name=pharmacy.name,
                        unit_price=price.unit_price,
                        subtotal=round(med.quantity * price.unit_price, 2),
                        currency=CURRENCY,
                        rating=pharmacy.rating,
                        distance_km=distance_km,
                        eta_minutes=eta_minutes,
                    )
                )
            offers.sort(key=lambda offer: offer.unit_price)

        lines.append(
            MedicationPricingLineOut(
                medication_id=med.id,
                name=med.name,
                dosage=med.dosage,
                dosage_unit=med.dosage_unit,
                quantity=med.quantity,
                offers=offers,
            )
        )

    return lines
