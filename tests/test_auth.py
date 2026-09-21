import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.order import Order
from app.models.pharmacy import (
    DosageUnit,
    MedicationCatalog,
    MedicationForm,
    MedicationType,
    Pharmacy,
    PharmacyProduct,
)
from app.models.prescription import Medication, Prescription
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import FakeSmsSender
from tests.helpers import PHONE, get_otp_code, signup


async def test_otp_request_then_verify_returns_verification_token(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    code = await get_otp_code(client, fake_sms)
    resp = await client.post("/v1/auth/otp/verify", json={"phone_number": PHONE, "code": code})
    assert resp.status_code == 200
    assert "verification_token" in resp.json()


async def test_otp_verify_wrong_code_fails(client: AsyncClient, fake_sms: FakeSmsSender) -> None:
    await get_otp_code(client, fake_sms)
    resp = await client.post("/v1/auth/otp/verify", json={"phone_number": PHONE, "code": "000000"})
    assert resp.status_code == 400
    assert "message" in resp.json()


async def test_otp_request_rate_limited_on_cooldown(
    client: AsyncClient, fake_sms: FakeSmsSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "otp_request_cooldown_seconds", 60)

    resp1 = await client.post("/v1/auth/otp/request", json={"phone_number": PHONE})
    assert resp1.status_code == 204
    resp2 = await client.post("/v1/auth/otp/request", json={"phone_number": PHONE})
    assert resp2.status_code == 429
    assert "message" in resp2.json()


async def test_register_happy_path(client: AsyncClient, fake_sms: FakeSmsSender) -> None:
    body = await signup(client, fake_sms)
    assert body["user"]["phone_number"] == PHONE
    assert body["user"]["full_name"] == "August Mensah"
    assert "access_token" in body
    assert "refresh_token" in body
    assert "pin" not in body["user"]
    assert "pin_hash" not in body["user"]


async def test_register_duplicate_phone_number_conflicts(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    # Simulates two concurrent signup attempts for the same phone number:
    # both obtain a "signup" verification token before either registers.
    code_1 = await get_otp_code(client, fake_sms)
    token_1 = (
        await client.post("/v1/auth/otp/verify", json={"phone_number": PHONE, "code": code_1})
    ).json()["verification_token"]

    code_2 = await get_otp_code(client, fake_sms)
    token_2 = (
        await client.post("/v1/auth/otp/verify", json={"phone_number": PHONE, "code": code_2})
    ).json()["verification_token"]

    first = await client.post(
        "/v1/auth/register",
        json={
            "verification_token": token_1,
            "phone_number": PHONE,
            "full_name": "August Mensah",
            "pin": "123456",
        },
    )
    assert first.status_code == 201

    second = await client.post(
        "/v1/auth/register",
        json={
            "verification_token": token_2,
            "phone_number": PHONE,
            "full_name": "Someone Else",
            "pin": "111111",
        },
    )
    assert second.status_code == 409


async def test_login_happy_path(client: AsyncClient, fake_sms: FakeSmsSender) -> None:
    await signup(client, fake_sms)
    resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "123456"})
    assert resp.status_code == 200
    assert resp.json()["user"]["phone_number"] == PHONE


async def test_login_wrong_pin_fails_with_client_message_shape(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    await signup(client, fake_sms)
    resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "999999"})
    assert resp.status_code == 401
    assert resp.json() == {"message": "PIN doesn't match. Please try again."}


async def test_login_locks_out_after_max_failed_attempts(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    await signup(client, fake_sms)
    for _ in range(5):
        resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "999999"})
        assert resp.status_code == 401

    locked_resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "123456"})
    assert locked_resp.status_code == 423


async def test_pin_reset_happy_path(client: AsyncClient, fake_sms: FakeSmsSender) -> None:
    await signup(client, fake_sms)

    code = await get_otp_code(client, fake_sms)
    verify_resp = await client.post(
        "/v1/auth/otp/verify", json={"phone_number": PHONE, "code": code}
    )
    verification_token = verify_resp.json()["verification_token"]

    reset_resp = await client.post(
        "/v1/auth/pin/reset", json={"verification_token": verification_token, "pin": "654321"}
    )
    assert reset_resp.status_code == 200

    login_resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "654321"})
    assert login_resp.status_code == 200

    old_pin_resp = await client.post(
        "/v1/auth/login", json={"phone_number": PHONE, "pin": "123456"}
    )
    assert old_pin_resp.status_code == 401


async def test_pin_verify_happy_path_and_mismatch(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    await signup(client, fake_sms)

    ok_resp = await client.post(
        "/v1/auth/pin/verify", json={"phone_number": PHONE, "pin": "123456"}
    )
    assert ok_resp.status_code == 200

    bad_resp = await client.post(
        "/v1/auth/pin/verify", json={"phone_number": PHONE, "pin": "000000"}
    )
    assert bad_resp.status_code == 401


async def test_pin_change_requires_auth_and_correct_current_pin(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    access_token = session["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    unauthenticated = await client.post(
        "/v1/auth/pin/change",
        json={"phone_number": PHONE, "current_pin": "123456", "new_pin": "654321"},
    )
    assert unauthenticated.status_code == 401

    wrong_current = await client.post(
        "/v1/auth/pin/change",
        json={"phone_number": PHONE, "current_pin": "000000", "new_pin": "654321"},
        headers=headers,
    )
    assert wrong_current.status_code == 401

    ok = await client.post(
        "/v1/auth/pin/change",
        json={"phone_number": PHONE, "current_pin": "123456", "new_pin": "654321"},
        headers=headers,
    )
    assert ok.status_code == 200

    relogin = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "654321"})
    assert relogin.status_code == 200


async def test_token_refresh_rotates_and_invalidates_old_token(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    refresh_token = session["refresh_token"]

    resp = await client.post("/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != refresh_token

    reuse_resp = await client.post("/v1/auth/token/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401


async def test_get_me_requires_auth_and_returns_profile(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    access_token = session["access_token"]

    unauthenticated = await client.get("/v1/me")
    assert unauthenticated.status_code == 401

    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["phone_number"] == PHONE


async def test_patch_me_updates_only_provided_fields(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    resp = await client.patch("/v1/me", json={"address": "12 Independence Ave"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["address"] == "12 Independence Ave"
    assert body["full_name"] == "August Mensah"


async def test_delete_me_removes_account(client: AsyncClient, fake_sms: FakeSmsSender) -> None:
    session = await signup(client, fake_sms)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    resp = await client.delete("/v1/me", headers=headers)
    assert resp.status_code == 204

    login_resp = await client.post("/v1/auth/login", json={"phone_number": PHONE, "pin": "123456"})
    assert login_resp.status_code == 401


async def test_delete_me_then_get_me_with_old_token_is_401(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    delete_resp = await client.delete("/v1/me", headers=headers)
    assert delete_resp.status_code == 204

    # Same still-valid (not yet expired) access token -- must not keep
    # working just because it hasn't expired yet.
    get_resp = await client.get("/v1/me", headers=headers)
    assert get_resp.status_code == 401


async def test_delete_me_cascades_related_rows(
    client: AsyncClient, fake_sms: FakeSmsSender, db_session: AsyncSession
) -> None:
    session = await signup(client, fake_sms)
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    user_id = session["user"]["id"]

    async def _get_or_create(model: type, name: str):
        existing = (
            await db_session.execute(select(model).where(model.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = model(name=name)
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)
        return row

    pharmacy = Pharmacy(name="Test Pharmacy", latitude=5.6, longitude=-0.18)
    db_session.add(pharmacy)
    unit_row = await _get_or_create(DosageUnit, "mg")
    form_row = await _get_or_create(MedicationForm, "tablet")
    type_row = await _get_or_create(MedicationType, "pills")
    catalog = MedicationCatalog(
        name="Amoxicillin",
        dosage="500",
        unit_id=unit_row.id,
        form_id=form_row.id,
        type_id=type_row.id,
    )
    db_session.add(catalog)
    await db_session.commit()
    await db_session.refresh(pharmacy)
    await db_session.refresh(catalog)
    db_session.add(PharmacyProduct(pharmacy_id=pharmacy.id, catalog_id=catalog.id, unit_price=2.0))
    await db_session.commit()

    medications = [
        {
            "id": "client-uuid",
            "name": "Amoxicillin",
            "dosage": "500",
            "dosage_unit": "mg",
            "quantity": 5,
            "quantity_unit": "capsule",
            "type": "pills",
            "dose_amount": 1,
            "duration_days": 5,
            "reminder_enabled": False,
            "notification_days": [],
            "frequency": "Once Daily",
            "times": ["8:00 AM"],
            "start_from": "2026-09-16T08:00:00.000",
            "end_on": "2026-09-21T08:00:00.000",
        }
    ]
    submit_resp = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps(medications)},
        headers=headers,
    )
    assert submit_resp.status_code == 201
    prescription_id = submit_resp.json()["id"]

    order_resp = await client.post(
        "/v1/orders",
        json={
            "prescription_id": prescription_id,
            "pharmacy_id": pharmacy.id,
            "payment_type": "cashOnDelivery",
        },
        headers=headers,
    )
    assert order_resp.status_code == 201

    # Sanity check: everything actually exists before deleting.
    assert (
        await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
    ).scalars().first() is not None
    assert (
        await db_session.execute(select(Prescription).where(Prescription.id == prescription_id))
    ).scalars().first() is not None
    assert (
        await db_session.execute(
            select(Medication).where(Medication.prescription_id == prescription_id)
        )
    ).scalars().first() is not None
    assert (
        await db_session.execute(select(Order).where(Order.user_id == user_id))
    ).scalars().first() is not None

    delete_resp = await client.delete("/v1/me", headers=headers)
    assert delete_resp.status_code == 204

    assert (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalars().first() is None
    assert (
        await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
    ).scalars().first() is None
    assert (
        await db_session.execute(select(Prescription).where(Prescription.id == prescription_id))
    ).scalars().first() is None
    assert (
        await db_session.execute(
            select(Medication).where(Medication.prescription_id == prescription_id)
        )
    ).scalars().first() is None
    assert (
        await db_session.execute(select(Order).where(Order.user_id == user_id))
    ).scalars().first() is None
