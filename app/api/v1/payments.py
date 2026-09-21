from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.payments import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    VerifyPaymentResponse,
)
from app.services import payment_service

router = APIRouter(prefix="/payments/paystack", tags=["payments"])


@router.post("/initialize", response_model=InitializePaymentResponse)
async def initialize(
    payload: InitializePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InitializePaymentResponse:
    """Idempotent on reference -- a retry with the same client-supplied
    reference returns the existing checkout session instead of calling
    Paystack again.
    """
    return await payment_service.initialize_payment(db, current_user.id, payload)


@router.get("/verify/{reference}", response_model=VerifyPaymentResponse)
async def verify(
    reference: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VerifyPaymentResponse:
    status_value = await payment_service.verify_payment(db, current_user.id, reference)
    return VerifyPaymentResponse(status=status_value)


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    x_paystack_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Called by Paystack's servers, not a logged-in user -- no Bearer
    auth here. The signature header is the only trust boundary.
    """
    body = await request.body()
    await payment_service.handle_webhook(db, body, x_paystack_signature)
    return {"received": True}
