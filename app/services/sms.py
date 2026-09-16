import logging
from typing import Protocol

logger = logging.getLogger("pharmly.sms")


class SmsSender(Protocol):
    async def send_otp(self, phone_number: str, code: str) -> None: ...


class LoggingSmsSender:
    """Dev-only stand-in. No SMS provider has been chosen yet (PRD §9) —
    swap this for a real provider (Twilio / Africa's Talking / etc.) once
    the product owner picks one and credentials are provisioned.
    """

    async def send_otp(self, phone_number: str, code: str) -> None:
        logger.info("OTP for %s: %s (no SMS provider configured)", phone_number, code)


def get_sms_sender() -> SmsSender:
    return LoggingSmsSender()
