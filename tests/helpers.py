from httpx import AsyncClient

from tests.conftest import FakeSmsSender

PHONE = "+233241234567"


async def get_otp_code(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> str:
    resp = await client.post("/v1/auth/otp/request", json={"phone_number": phone})
    assert resp.status_code == 204
    return fake_sms.sent[phone]


async def signup(client: AsyncClient, fake_sms: FakeSmsSender, phone: str = PHONE) -> dict:
    code = await get_otp_code(client, fake_sms, phone)
    verify_resp = await client.post(
        "/v1/auth/otp/verify", json={"phone_number": phone, "code": code}
    )
    assert verify_resp.status_code == 200
    verification_token = verify_resp.json()["verification_token"]

    register_resp = await client.post(
        "/v1/auth/register",
        json={
            "verification_token": verification_token,
            "phone_number": phone,
            "full_name": "August Mensah",
            "email": "august@example.com",
            "pin": "123456",
        },
    )
    assert register_resp.status_code == 201
    return register_resp.json()
