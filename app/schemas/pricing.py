from typing import Literal

from pydantic import BaseModel


class PricingRequest(BaseModel):
    prescription_id: str
    order_type: Literal["singleLine", "multiLine"]
    # Not in the PRD's documented request shape -- added so distance_km/
    # eta_minutes can be computed without a geocoding provider. The mobile
    # app already collects device location; needs sign-off before shipping.
    latitude: float | None = None
    longitude: float | None = None


class PharmacyOfferOut(BaseModel):
    """singleLine response: one bundled quote per pharmacy."""

    pharmacy_id: str
    pharmacy_name: str
    total_price: float
    currency: str
    is_fully_in_stock: bool
    rating: float | None
    distance_km: float | None
    eta_minutes: int | None


class MedicationLineOfferOut(BaseModel):
    """multiLine response: one pharmacy's quote for a single medication."""

    pharmacy_id: str
    pharmacy_name: str
    unit_price: float
    subtotal: float
    currency: str
    rating: float | None
    distance_km: float | None
    eta_minutes: int | None


class MedicationPricingLineOut(BaseModel):
    """multiLine response: one medication and every pharmacy that carries it."""

    medication_id: str
    name: str
    dosage: str
    dosage_unit: str
    quantity: int
    offers: list[MedicationLineOfferOut]
