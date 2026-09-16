import json

import httpx
import pytest

from app.core.config import settings
from app.services.sms import ArkeselSmsSender, LoggingSmsSender, SmsSendError, get_sms_sender


def _mock_transport(handler):
    return httpx.MockTransport(handler)


async def test_arkesel_sends_expected_payload_and_headers():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "success", "data": {"id": "msg_1"}})

    sender = ArkeselSmsSender(
        api_key="test-key",
        sender_id="Pharmly",
        sandbox=True,
        transport=_mock_transport(handler),
    )
    await sender.send_otp("+233241234567", "123456")

    assert captured["url"] == "https://sms.arkesel.com/api/v2/sms/send"
    assert captured["headers"]["api-key"] == "test-key"
    assert captured["body"]["recipients"] == ["233241234567"]
    assert captured["body"]["sandbox"] is True
    assert "123456" in captured["body"]["message"]


async def test_arkesel_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "error", "message": "invalid api key"})

    sender = ArkeselSmsSender(
        api_key="bad-key", sender_id="Pharmly", sandbox=True, transport=_mock_transport(handler)
    )
    with pytest.raises(SmsSendError):
        await sender.send_otp("+233241234567", "123456")


async def test_arkesel_raises_on_non_success_status_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "message": "insufficient balance"})

    sender = ArkeselSmsSender(
        api_key="test-key", sender_id="Pharmly", sandbox=True, transport=_mock_transport(handler)
    )
    with pytest.raises(SmsSendError):
        await sender.send_otp("+233241234567", "123456")


def test_get_sms_sender_defaults_to_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sms_provider", "console")
    assert isinstance(get_sms_sender(), LoggingSmsSender)


def test_get_sms_sender_requires_api_key_for_arkesel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sms_provider", "arkesel")
    monkeypatch.setattr(settings, "arkesel_api_key", None)
    with pytest.raises(RuntimeError):
        get_sms_sender()


def test_get_sms_sender_sandboxes_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sms_provider", "arkesel")
    monkeypatch.setattr(settings, "arkesel_api_key", "test-key")
    monkeypatch.setattr(settings, "arkesel_sandbox", None)

    monkeypatch.setattr(settings, "environment", "staging")
    sender = get_sms_sender()
    assert isinstance(sender, ArkeselSmsSender)
    assert sender._sandbox is True

    monkeypatch.setattr(settings, "environment", "prod")
    sender = get_sms_sender()
    assert sender._sandbox is False


def test_get_sms_sender_explicit_sandbox_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "sms_provider", "arkesel")
    monkeypatch.setattr(settings, "arkesel_api_key", "test-key")
    monkeypatch.setattr(settings, "environment", "prod")
    monkeypatch.setattr(settings, "arkesel_sandbox", True)

    sender = get_sms_sender()
    assert sender._sandbox is True
