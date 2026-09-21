from httpx import AsyncClient

from tests.conftest import FakeSmsSender
from tests.helpers import signup


async def test_bad_phone_number_format_gives_specific_message(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/otp/request", json={"phone_number": "233244245902"})
    assert resp.status_code == 422
    assert resp.json() == {
        "message": "Phone number must be in international format, e.g. +233XXXXXXXXX."
    }


async def test_bad_pin_format_gives_specific_message(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/auth/login", json={"phone_number": "+233244245902", "pin": "12"}
    )
    assert resp.status_code == 422
    assert resp.json() == {"message": "PIN must be exactly 6 digits."}


async def test_missing_field_gives_specific_message(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/otp/request", json={})
    assert resp.status_code == 422
    assert resp.json() == {"message": "'phone_number' is required."}


async def test_bad_literal_value_gives_specific_message(
    client: AsyncClient, fake_sms: FakeSmsSender
) -> None:
    session = await signup(client, fake_sms)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    resp = await client.post(
        "/v1/orders/pricing",
        json={"prescription_id": "x", "order_type": "wrongType"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json() == {
        "message": "'order_type' must be one of: 'singleLine' or 'multiLine'."
    }
