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
    """singleLine: one bundled quote per pharmacy (medication_id is null).

    multiLine: one row per (medication, pharmacy-that-carries-it) pair --
    total_price is that single medication's line price at this pharmacy,
    medication_id groups rows on the client. Same response type for both
    modes: the mobile client's PharmacyOffer.fromJson parses a flat array
    either way.
    """

    pharmacy_id: str
    pharmacy_name: str
    total_price: float
    currency: str
    is_fully_in_stock: bool
    rating: float | None
    distance_km: float | None
    eta_minutes: int | None
    medication_id: str | None = None
