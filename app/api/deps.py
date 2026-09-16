import jwt
from fastapi import Depends, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApiError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Authentication required.")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError as err:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again."
        ) from err

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")
    return user
