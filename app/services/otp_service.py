from datetime import timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import generate_otp_code, hash_otp, verify_otp_code
from app.core.time import utcnow
from app.models.otp import OtpCode
from app.services.sms import get_sms_sender


async def request_otp(db: AsyncSession, phone_number: str) -> None:
    now = utcnow()

    recent = await db.execute(
        select(OtpCode)
        .where(OtpCode.phone_number == phone_number)
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    last_code = recent.scalar_one_or_none()
    if last_code and (now - last_code.created_at) < timedelta(
        seconds=settings.otp_request_cooldown_seconds
    ):
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Please wait before requesting another code.",
        )

    hour_ago = now - timedelta(hours=1)
    count_result = await db.execute(
        select(OtpCode).where(
            OtpCode.phone_number == phone_number, OtpCode.created_at >= hour_ago
        )
    )
    if len(count_result.scalars().all()) >= settings.otp_request_max_per_hour:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many code requests. Please try again later.",
        )

    code = generate_otp_code()
    otp = OtpCode(
        phone_number=phone_number,
        code_hash=hash_otp(code),
        purpose="verify",
        expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.commit()

    await get_sms_sender().send_otp(phone_number, code)


async def verify_otp(db: AsyncSession, phone_number: str, code: str) -> None:
    now = utcnow()
    result = await db.execute(
        select(OtpCode)
        .where(
            OtpCode.phone_number == phone_number,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at >= now,
        )
        .order_by(OtpCode.created_at.desc())
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        if verify_otp_code(code, candidate.code_hash):
            candidate.consumed_at = now
            await db.commit()
            return

    raise ApiError(status.HTTP_400_BAD_REQUEST, "That code is incorrect or has expired.")
