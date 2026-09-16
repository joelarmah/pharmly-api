import logging
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger("pharmly.sms")


class SmsSender(Protocol):
    async def send_otp(self, phone_number: str, code: str) -> None: ...


class SmsSendError(RuntimeError):
    """Raised when a configured provider fails to accept/send a message."""


class LoggingSmsSender:
    """Dev-only stand-in used when no real provider is configured."""

    async def send_otp(self, phone_number: str, code: str) -> None:
        logger.info("OTP for %s: %s (no SMS provider configured)", phone_number, code)


class ArkeselSmsSender:
    """Sends OTP SMS via Arkesel's v2 API (https://developers.arkesel.com).

    Provider-specific details (endpoint, headers, payload shape) are
    confined to this class -- everything else in the app only ever sees
    the SmsSender protocol -- so swapping providers later is a matter of
    adding a new class here and pointing get_sms_sender() at it.
    """

    _ENDPOINT = "https://sms.arkesel.com/api/v2/sms/send"

    def __init__(
        self,
        api_key: str,
        sender_id: str,
        sandbox: bool,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender_id = sender_id
        self._sandbox = sandbox
        self._transport = transport  # test hook only; None uses the real network

    async def send_otp(self, phone_number: str, code: str) -> None:
        # Arkesel expects bare MSISDNs (e.g. "233544919953"), not E.164's
        # leading "+" -- every example in their spec drops it.
        recipient = phone_number.removeprefix("+")
        payload = {
            "sender": self._sender_id,
            "message": (
                f"Your Pharmly verification code is {code}. "
                f"It expires in {settings.otp_expire_minutes} minutes."
            ),
            "recipients": [recipient],
            "sandbox": self._sandbox,
        }
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
            response = await client.post(self._ENDPOINT, json=payload, headers=headers)

        if response.status_code >= 400:
            logger.error(
                "Arkesel SMS send failed: %s %s", response.status_code, response.text
            )
            raise SmsSendError("SMS provider rejected the request.")

        body = response.json()
        if body.get("status") != "success":
            logger.error("Arkesel SMS send returned a non-success status: %s", body)
            raise SmsSendError("SMS provider did not confirm the send.")


def get_sms_sender() -> SmsSender:
    if settings.sms_provider == "arkesel":
        if not settings.arkesel_api_key:
            raise RuntimeError("ARKESEL_API_KEY is not configured.")
        sandbox = (
            settings.arkesel_sandbox
            if settings.arkesel_sandbox is not None
            else settings.environment != "prod"
        )
        return ArkeselSmsSender(
            api_key=settings.arkesel_api_key,
            sender_id=settings.arkesel_sender_id,
            sandbox=sandbox,
        )
    return LoggingSmsSender()
