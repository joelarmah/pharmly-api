import hashlib
import hmac
import json

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models.payment import PaymentTransaction
from app.schemas.payments import InitializePaymentRequest
from app.services import payment_service
from tests.conftest import FakeSmsSender
from tests.helpers import PHONE, signup

TEST_SECRET = "sk_test_fake_secret_for_tests"


@pytest.fixture(autouse=True)
def _paystack_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "paystack_secret_key", TEST_SECRET)


async def _user_id(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> str:
    session = await signup(client, fake_sms, phone)
    return session["user"]["id"]


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _paystack_initialize_response(reference: str) -> dict:
    return {
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": f"https://checkout.paystack.com/{reference}",
            "access_code": "access_code_123",
            "reference": reference,
        },
    }


def _paystack_verify_response(reference: str, status_value: str) -> dict:
    return {
        "status": True,
        "message": "Verification successful",
        "data": {"reference": reference, "status": status_value, "amount": 10000},
    }


async def test_initialize_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/payments/paystack/initialize",
        json={"amount": 100.0, "email": "a@b.com"},
    )
    assert resp.status_code == 401


async def test_initialize_happy_path(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_id = await _user_id(client, fake_sms)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["amount"] == 10000  # 100.00 GHS -> 10000 pesewas
        assert body["currency"] == "GHS"
        return httpx.Response(200, json=_paystack_initialize_response(body["reference"]))

    result = await payment_service.initialize_payment(
        db_session,
        user_id,
        InitializePaymentRequest(amount=100.0, email="a@b.com"),
        transport=_mock_transport(handler),
    )
    assert result.reference.startswith("PSK-")
    assert result.checkout_url == f"https://checkout.paystack.com/{result.reference}"
    assert len(calls) == 1

    row = (
        await db_session.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == result.reference)
        )
    ).scalar_one()
    assert row.status == "pending"
    assert row.amount == 100.0
    assert row.user_id == user_id


async def test_initialize_idempotent_on_same_reference(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_id = await _user_id(client, fake_sms)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_paystack_initialize_response("PSK-fixed"))

    payload = InitializePaymentRequest(amount=50.0, email="a@b.com", reference="PSK-fixed")
    first = await payment_service.initialize_payment(
        db_session, user_id, payload, transport=_mock_transport(handler)
    )
    second = await payment_service.initialize_payment(
        db_session, user_id, payload, transport=_mock_transport(handler)
    )

    assert first.reference == second.reference == "PSK-fixed"
    assert first.checkout_url == second.checkout_url
    assert len(calls) == 1  # second call short-circuited, never hit Paystack


async def test_verify_happy_path(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_id = await _user_id(client, fake_sms)

    def init_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_paystack_initialize_response("PSK-verify-1"))

    result = await payment_service.initialize_payment(
        db_session,
        user_id,
        InitializePaymentRequest(amount=100.0, email="a@b.com", reference="PSK-verify-1"),
        transport=_mock_transport(init_handler),
    )

    def verify_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_paystack_verify_response(result.reference, "success"))

    status_value = await payment_service.verify_payment(
        db_session, user_id, result.reference, transport=_mock_transport(verify_handler)
    )
    assert status_value == "success"

    row = (
        await db_session.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == result.reference)
        )
    ).scalar_one()
    assert row.status == "success"


async def test_verify_uses_cache_within_window(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_id = await _user_id(client, fake_sms)

    def init_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_paystack_initialize_response("PSK-cache-1"))

    result = await payment_service.initialize_payment(
        db_session,
        user_id,
        InitializePaymentRequest(amount=100.0, email="a@b.com", reference="PSK-cache-1"),
        transport=_mock_transport(init_handler),
    )

    calls = []

    def verify_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_paystack_verify_response(result.reference, "success"))

    await payment_service.verify_payment(
        db_session, user_id, result.reference, transport=_mock_transport(verify_handler)
    )
    await payment_service.verify_payment(
        db_session, user_id, result.reference, transport=_mock_transport(verify_handler)
    )
    assert len(calls) == 1  # second call served from the cache window


async def test_verify_404_on_someone_elses_reference(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_a = await _user_id(client, fake_sms, "+233241111111")
    user_b = await _user_id(client, fake_sms, "+233242222222")

    def init_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_paystack_initialize_response("PSK-owner-1"))

    result = await payment_service.initialize_payment(
        db_session,
        user_a,
        InitializePaymentRequest(amount=100.0, email="a@b.com", reference="PSK-owner-1"),
        transport=_mock_transport(init_handler),
    )

    with pytest.raises(ApiError) as exc_info:
        await payment_service.verify_payment(db_session, user_b, result.reference)
    assert exc_info.value.status_code == 404


async def test_webhook_rejects_bad_signature(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = json.dumps(
        {"event": "charge.success", "data": {"reference": "PSK-x", "status": "success"}}
    )
    resp = await client.post(
        "/v1/payments/paystack/webhook",
        content=body,
        headers={"x-paystack-signature": "wrong-signature", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


async def test_webhook_accepts_valid_signature_and_updates_status(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    user_id = await _user_id(client, fake_sms)

    def init_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_paystack_initialize_response("PSK-webhook-1"))

    result = await payment_service.initialize_payment(
        db_session,
        user_id,
        InitializePaymentRequest(amount=100.0, email="a@b.com", reference="PSK-webhook-1"),
        transport=_mock_transport(init_handler),
    )

    body_dict = {
        "event": "charge.success",
        "data": {"reference": result.reference, "status": "success", "amount": 10000},
    }
    body = json.dumps(body_dict).encode()
    signature = hmac.new(TEST_SECRET.encode(), body, hashlib.sha512).hexdigest()

    resp = await client.post(
        "/v1/payments/paystack/webhook",
        content=body,
        headers={"x-paystack-signature": signature, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    row = (
        await db_session.execute(
            select(PaymentTransaction).where(PaymentTransaction.reference == result.reference)
        )
    ).scalar_one()
    assert row.status == "success"
