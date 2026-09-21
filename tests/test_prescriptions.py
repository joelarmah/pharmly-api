import json

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import FakeSmsSender
from tests.helpers import signup

MEDICATION = {
    "id": "client-generated-uuid",
    "name": "Amoxicillin",
    "dosage": "500",
    "dosage_unit": "mg",
    "quantity": 21,
    "quantity_unit": "capsule",
    "type": "pills",
    "dose_amount": 1,
    "duration_days": 7,
    "reminder_enabled": True,
    "notification_days": ["Mon", "Wed", "Fri"],
    "frequency": "Twice Daily",
    "times": ["8:00 AM", "8:00 PM"],
    "start_from": "2026-09-16T08:00:00.000",
    "end_on": "2026-09-23T20:00:00.000",
}


@pytest.fixture(autouse=True)
def _local_storage_tmp_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))


async def _auth_headers(client: AsyncClient, fake_sms: FakeSmsSender) -> dict:
    session = await signup(client, fake_sms)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def test_submit_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/prescriptions/submit", data={"medications": json.dumps([MEDICATION])}
    )
    assert resp.status_code == 401


async def test_submit_without_image_happy_path(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    resp = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([MEDICATION])},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["image_url"] is None
    assert len(body["medications"]) == 1
    med = body["medications"][0]
    assert med["name"] == "Amoxicillin"
    assert med["id"] != "client-generated-uuid"  # server assigns its own id
    assert med["notification_days"] == ["Mon", "Wed", "Fri"]
    assert med["times"] == ["8:00 AM", "8:00 PM"]


async def test_submit_with_image_stores_and_returns_url(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    resp = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([MEDICATION])},
        files={"image": ("scan.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["image_url"] is not None
    assert body["image_url"].endswith(".jpg")
    assert body["id"] in body["image_url"]


async def test_submit_rejects_unsupported_image_type(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    resp = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([MEDICATION])},
        files={"image": ("scan.pdf", b"not-an-image", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "message" in resp.json()


async def test_submit_rejects_empty_medications(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    resp = await client.post(
        "/v1/prescriptions/submit", data={"medications": json.dumps([])}, headers=headers
    )
    assert resp.status_code == 422


async def test_submit_rejects_invalid_medications_json(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    resp = await client.post(
        "/v1/prescriptions/submit", data={"medications": "not-json"}, headers=headers
    )
    assert resp.status_code == 422
    assert "message" in resp.json()


async def test_get_prescriptions_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/v1/prescriptions")
    assert resp.status_code == 401


async def test_get_prescriptions_returns_only_own_newest_first(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    headers = await _auth_headers(client, fake_sms)

    other_medication = {**MEDICATION, "name": "Paracetamol"}
    first = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([MEDICATION])},
        headers=headers,
    )
    second = await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([other_medication])},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201

    resp = await client.get("/v1/prescriptions", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == second.json()["id"]
    assert body[1]["id"] == first.json()["id"]


async def test_get_prescriptions_does_not_leak_other_users(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import otp_service

    fake_sms_a = FakeSmsSender()
    fake_sms_b = FakeSmsSender()

    monkeypatch.setattr(otp_service, "get_sms_sender", lambda: fake_sms_a)
    session_a = await signup(client, fake_sms_a, phone="+233241234567")
    monkeypatch.setattr(otp_service, "get_sms_sender", lambda: fake_sms_b)
    session_b = await signup(client, fake_sms_b, phone="+233247654321")

    headers_a = {"Authorization": f"Bearer {session_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {session_b['access_token']}"}

    await client.post(
        "/v1/prescriptions/submit",
        data={"medications": json.dumps([MEDICATION])},
        headers=headers_a,
    )

    resp_b = await client.get("/v1/prescriptions", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json() == []
