from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.orders import OrderOut, PlaceOrderRequest, PlaceOrderResponse
from app.schemas.pricing import MedicationPricingLineOut, PharmacyOfferOut, PricingRequest
from app.services import order_service, pricing_service

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


@router.post("", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: PlaceOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaceOrderResponse:
    """Idempotent on prescription_id -- a prescription can only ever
    produce one order, so a retry (same or different pharmacy_id) returns
    the order that already exists instead of erroring or duplicating.
    """
    order = await order_service.place_order(db, current_user.id, payload)
    return PlaceOrderResponse(order_id=order.id)


@router.get("", response_model=list[OrderOut])
async def get_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[OrderOut]:
    return await order_service.list_orders(db, current_user.id)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderOut:
    return await order_service.get_order(db, current_user.id, order_id)
