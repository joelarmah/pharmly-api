from datetime import timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.core.time import utcnow
from app.models.phone_lookup_attempt import PhoneLookupAttempt
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def issue_session_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id)

    raw_refresh = generate_refresh_token()
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(refresh)
    await db.commit()

    return access_token, raw_refresh


def assert_pin_not_locked(user: User) -> None:
    if user.pin_locked_until and user.pin_locked_until > utcnow():
        raise ApiError(
            status.HTTP_423_LOCKED,
            "Too many incorrect attempts. Please try again later.",
        )


async def register_pin_failure(db: AsyncSession, user: User) -> None:
    user.pin_failed_attempts += 1
    if user.pin_failed_attempts >= settings.pin_max_failed_attempts:
        user.pin_locked_until = utcnow() + timedelta(minutes=settings.pin_lockout_minutes)
        user.pin_failed_attempts = 0
    await db.commit()


async def reset_pin_failures(db: AsyncSession, user: User) -> None:
    if user.pin_failed_attempts or user.pin_locked_until:
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        await db.commit()


async def check_phone_lookup_rate_limit(db: AsyncSession, phone_number: str) -> None:
    now = utcnow()

    recent = await db.execute(
        select(PhoneLookupAttempt)
        .where(PhoneLookupAttempt.phone_number == phone_number)
        .order_by(PhoneLookupAttempt.created_at.desc())
        .limit(1)
    )
    last_attempt = recent.scalar_one_or_none()
    if last_attempt and (now - last_attempt.created_at) < timedelta(
        seconds=settings.phone_lookup_cooldown_seconds
    ):
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Please wait before checking again.",
        )

    hour_ago = now - timedelta(hours=1)
    count_result = await db.execute(
        select(PhoneLookupAttempt).where(
            PhoneLookupAttempt.phone_number == phone_number,
            PhoneLookupAttempt.created_at >= hour_ago,
        )
    )
    if len(count_result.scalars().all()) >= settings.phone_lookup_max_per_hour:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please try again later.",
        )

    db.add(PhoneLookupAttempt(phone_number=phone_number))
    await db.commit()
