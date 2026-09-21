import json
import logging

import httpx
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.ids import generate_id
from app.core.security import verify_paystack_signature
from app.core.time import utcnow
from app.models.payment import PaymentTransaction
from app.schemas.payments import InitializePaymentRequest, InitializePaymentResponse

logger = logging.getLogger("pharmly.payments")

_API_BASE = "https://api.paystack.co"
CURRENCY = "GHS"

# Paystack's own statuses are richer than the pending|success|failed shape
# the PRD wants on our side. Verified live against the real test API:
# a freshly-initialized, completely untouched transaction already reports
# "abandoned" -- it's Paystack's generic "nothing completed yet" bucket,
# not a reliable failure signal, and mapping it to "failed" would show a
# false "Payment failed" to a client mid-poll while the user is still
# filling in card details. Only Paystack's explicit "failed" counts as
# failed; everything else not "success" stays "pending" so polling keeps
# waiting rather than giving up early.
_SUCCESS_STATUSES = {"success"}
_FAILED_STATUSES = {"failed"}


class PaystackError(RuntimeError):
    """Raised when Paystack's API rejects or fails a request."""


def _map_status(paystack_status: str) -> str:
    if paystack_status in _SUCCESS_STATUSES:
        return "success"
    if paystack_status in _FAILED_STATUSES:
        return "failed"
    return "pending"


def _headers() -> dict[str, str]:
    if not settings.paystack_secret_key:
        raise RuntimeError("PAYSTACK_SECRET_KEY is not configured.")
    return {
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json",
    }


async def initialize_payment(
    db: AsyncSession,
    user_id: str,
    payload: InitializePaymentRequest,
    transport: httpx.BaseTransport | None = None,
) -> InitializePaymentResponse:
    reference = payload.reference or f"PSK-{generate_id()}"

    existing = (
        await db.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == reference)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raw = existing.paystack_raw_response or {}
        checkout_url = raw.get("data", {}).get("authorization_url", "")
        return InitializePaymentResponse(reference=existing.reference, checkout_url=checkout_url)

    body = {
        "email": payload.email,
        "amount": round(payload.amount * 100),
        "reference": reference,
        "currency": CURRENCY,
    }
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        response = await client.post(
            f"{_API_BASE}/transaction/initialize", json=body, headers=_headers()
        )

    data = response.json()
    if response.status_code >= 400 or not data.get("status"):
        logger.error("Paystack initialize failed: %s %s", response.status_code, response.text)
        raise PaystackError("Paystack rejected the initialize request.")

    checkout_url = data["data"]["authorization_url"]
    db.add(
        PaymentTransaction(
            reference=reference,
            user_id=user_id,
            amount=payload.amount,
            status="pending",
            paystack_raw_response=data,
        )
    )
    await db.commit()

    return InitializePaymentResponse(reference=reference, checkout_url=checkout_url)


async def _load_owned_transaction(
    db: AsyncSession, user_id: str, reference: str
) -> PaymentTransaction:
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.reference == reference, PaymentTransaction.user_id == user_id
        )
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "Payment reference not found.")
    return transaction


async def verify_payment(
    db: AsyncSession,
    user_id: str,
    reference: str,
    transport: httpx.BaseTransport | None = None,
) -> str:
    transaction = await _load_owned_transaction(db, user_id, reference)

    if transaction.last_checked_at is not None:
        age = (utcnow() - transaction.last_checked_at).total_seconds()
        if age < settings.paystack_verify_cache_seconds:
            return transaction.status

    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        response = await client.get(
            f"{_API_BASE}/transaction/verify/{reference}", headers=_headers()
        )

    data = response.json()
    if response.status_code >= 400 or not data.get("status"):
        logger.error("Paystack verify failed: %s %s", response.status_code, response.text)
        raise PaystackError("Paystack rejected the verify request.")

    transaction.status = _map_status(data["data"]["status"])
    transaction.paystack_raw_response = data
    transaction.last_checked_at = utcnow()
    await db.commit()

    return transaction.status


async def handle_webhook(db: AsyncSession, payload: bytes, signature: str | None) -> None:
    if not settings.paystack_secret_key or not verify_paystack_signature(
        payload, signature, settings.paystack_secret_key
    ):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")

    event = json.loads(payload)
    data = event.get("data", {})
    reference = data.get("reference")
    if not reference:
        return

    transaction = (
        await db.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == reference)
        )
    ).scalar_one_or_none()
    if transaction is None:
        return

    transaction.status = _map_status(data.get("status", ""))
    transaction.paystack_raw_response = event
    transaction.last_checked_at = utcnow()
    await db.commit()
