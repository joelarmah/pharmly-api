from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApiError
from app.models.order import Order
from app.models.pharmacy import Pharmacy, PharmacyProduct
from app.models.prescription import Medication, Prescription
from app.schemas.orders import OrderOut, PlaceOrderRequest
from app.services.pricing_service import _load_owned_prescription, _match_catalog

_ORDER_LOAD_OPTIONS = (
    selectinload(Order.pharmacy),
    selectinload(Order.prescription).selectinload(Prescription.medications),
)


def _items_label(medications: list[Medication]) -> str:
    names = ", ".join(med.name for med in medications)
    count = len(medications)
    return f"{names} · {count} item{'' if count == 1 else 's'}"


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        pharmacy_name=order.pharmacy.name,
        items_label=_items_label(order.prescription.medications),
        progress=order.progress,
        placed_at=order.placed_at,
        total=order.total,
    )


async def _load_owned_order(db: AsyncSession, user_id: str, order_id: str) -> Order:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.user_id == user_id)
        .options(*_ORDER_LOAD_OPTIONS)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


async def _existing_order_for_prescription(db: AsyncSession, prescription_id: str) -> Order | None:
    result = await db.execute(
        select(Order).where(Order.prescription_id == prescription_id).options(*_ORDER_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def place_order(db: AsyncSession, user_id: str, payload: PlaceOrderRequest) -> OrderOut:
    prescription = await _load_owned_prescription(db, user_id, payload.prescription_id)

    existing = await _existing_order_for_prescription(db, prescription.id)
    if existing is not None:
        return _order_out(existing)

    pharmacy = (
        await db.execute(select(Pharmacy).where(Pharmacy.id == payload.pharmacy_id))
    ).scalar_one_or_none()
    if pharmacy is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Pharmacy not found.")

    total = 0.0
    for med in prescription.medications:
        catalog = await _match_catalog(db, med)
        if catalog is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"'{med.name}' isn't in the medication catalog.",
            )
        product = (
            await db.execute(
                select(PharmacyProduct).where(
                    PharmacyProduct.pharmacy_id == pharmacy.id,
                    PharmacyProduct.catalog_id == catalog.id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"'{pharmacy.name}' doesn't stock '{med.name}'.",
            )
        total += med.quantity * product.unit_price

    order = Order(
        user_id=user_id,
        prescription_id=prescription.id,
        pharmacy_id=pharmacy.id,
        payment_type=payload.payment_type,
        payment_reference=payload.payment_reference,
        total=round(total, 2),
    )
    prescription.status = "ordered"
    db.add(order)
    try:
        await db.commit()
    except IntegrityError:
        # Rare race: two concurrent identical requests both passed the
        # existing-order check above. The unique constraint on
        # prescription_id caught it -- fall back to the row the other
        # request just created instead of erroring.
        await db.rollback()
        existing = await _existing_order_for_prescription(db, prescription.id)
        if existing is not None:
            return _order_out(existing)
        raise

    placed = await _existing_order_for_prescription(db, prescription.id)
    assert placed is not None
    return _order_out(placed)


async def list_orders(db: AsyncSession, user_id: str) -> list[OrderOut]:
    result = await db.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .options(*_ORDER_LOAD_OPTIONS)
        .order_by(Order.placed_at.desc())
    )
    return [_order_out(order) for order in result.scalars().all()]


async def get_order(db: AsyncSession, user_id: str, order_id: str) -> OrderOut:
    order = await _load_owned_order(db, user_id, order_id)
    return _order_out(order)
