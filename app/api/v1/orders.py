from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.pricing import MedicationPricingLineOut, PharmacyOfferOut, PricingRequest
from app.services import pricing_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/pricing", response_model=list[PharmacyOfferOut] | list[MedicationPricingLineOut])
async def get_pricing(
    payload: PricingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PharmacyOfferOut] | list[MedicationPricingLineOut]:
    """Two different response shapes depending on `order_type`:

    - singleLine: one bundled PharmacyOffer per pharmacy for the whole
      prescription.
    - multiLine: one MedicationPricingLine per medication, each listing
      every pharmacy that carries it (no cross-pharmacy splitting logic --
      the client composes the final order from these).
    """
    if payload.order_type == "singleLine":
        return await pricing_service.price_bundle(
            db, current_user.id, payload.prescription_id, payload.latitude, payload.longitude
        )
    return await pricing_service.price_per_medication(
        db, current_user.id, payload.prescription_id, payload.latitude, payload.longitude
    )
