from datetime import timedelta

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.core.time import utcnow
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
