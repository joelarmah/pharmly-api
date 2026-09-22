import jwt
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import ApiError
from app.core.security import (
    create_verification_token,
    decode_verification_token,
    hash_pin,
    hash_refresh_token,
    verify_pin,
)
from app.core.time import utcnow
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    OtpRequest,
    OtpVerifyRequest,
    OtpVerifyResponse,
    PhoneLookupRequest,
    PhoneLookupResponse,
    PinChangeRequest,
    PinResetRequest,
    PinVerifyRequest,
    RegisterRequest,
    SessionResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from app.services import otp_service
from app.services.auth_service import (
    assert_pin_not_locked,
    check_phone_lookup_rate_limit,
    issue_session_tokens,
    register_pin_failure,
    reset_pin_failures,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_user_by_phone(db: AsyncSession, phone_number: str) -> User | None:
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    return result.scalar_one_or_none()


@router.post("/phone/lookup", response_model=PhoneLookupResponse)
async def lookup_phone(
    payload: PhoneLookupRequest, db: AsyncSession = Depends(get_db)
) -> PhoneLookupResponse:
    await check_phone_lookup_rate_limit(db, payload.phone_number)
    user = await _get_user_by_phone(db, payload.phone_number)
    return PhoneLookupResponse(registered=user is not None)


@router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(payload: OtpRequest, db: AsyncSession = Depends(get_db)) -> None:
    await otp_service.request_otp(db, payload.phone_number)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
async def verify_otp(
    payload: OtpVerifyRequest, db: AsyncSession = Depends(get_db)
) -> OtpVerifyResponse:
    await otp_service.verify_otp(db, payload.phone_number, payload.code)
    existing_user = await _get_user_by_phone(db, payload.phone_number)
    purpose = "forgot_pin" if existing_user else "signup"
    token = create_verification_token(payload.phone_number, purpose)
    return OtpVerifyResponse(verification_token=token)


_REVERIFY_MESSAGE = "Please verify your phone number again."


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> SessionResponse:
    try:
        phone_number = decode_verification_token(payload.verification_token, "signup")
    except jwt.PyJWTError as err:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, _REVERIFY_MESSAGE) from err

    if phone_number != payload.phone_number:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, _REVERIFY_MESSAGE)

    if await _get_user_by_phone(db, phone_number) is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT, "An account with this phone number already exists."
        )

    user = User(
        phone_number=phone_number,
        full_name=payload.full_name,
        email=payload.email,
        pin_hash=hash_pin(payload.pin),
    )
    db.add(user)
    await db.flush()

    access_token, refresh_token = await issue_session_tokens(db, user)
    return SessionResponse(access_token=access_token, refresh_token=refresh_token, user=user)


@router.post("/pin/reset", response_model=SessionResponse)
async def reset_pin(
    payload: PinResetRequest, db: AsyncSession = Depends(get_db)
) -> SessionResponse:
    try:
        phone_number = decode_verification_token(payload.verification_token, "forgot_pin")
    except jwt.PyJWTError as err:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, _REVERIFY_MESSAGE) from err

    user = await _get_user_by_phone(db, phone_number)
    if user is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "No account found for this phone number.")

    user.pin_hash = hash_pin(payload.pin)
    await reset_pin_failures(db, user)

    access_token, refresh_token = await issue_session_tokens(db, user)
    return SessionResponse(access_token=access_token, refresh_token=refresh_token, user=user)


@router.post("/login", response_model=SessionResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    user = await _get_user_by_phone(db, payload.phone_number)
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "PIN doesn't match. Please try again.")

    assert_pin_not_locked(user)

    if not verify_pin(payload.pin, user.pin_hash):
        await register_pin_failure(db, user)
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "PIN doesn't match. Please try again.")

    await reset_pin_failures(db, user)
    access_token, refresh_token = await issue_session_tokens(db, user)
    return SessionResponse(access_token=access_token, refresh_token=refresh_token, user=user)


@router.post("/pin/verify", status_code=status.HTTP_200_OK)
async def verify_pin_endpoint(
    payload: PinVerifyRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    user = await _get_user_by_phone(db, payload.phone_number)
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "PIN doesn't match. Please try again.")

    assert_pin_not_locked(user)

    if not verify_pin(payload.pin, user.pin_hash):
        await register_pin_failure(db, user)
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "PIN doesn't match. Please try again.")

    await reset_pin_failures(db, user)
    return {}


@router.post("/pin/change", response_model=SessionResponse)
async def change_pin(
    payload: PinChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    if payload.phone_number != current_user.phone_number:
        raise ApiError(status.HTTP_403_FORBIDDEN, "You can only change your own PIN.")

    assert_pin_not_locked(current_user)

    if not verify_pin(payload.current_pin, current_user.pin_hash):
        await register_pin_failure(db, current_user)
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "PIN doesn't match. Please try again.")

    await reset_pin_failures(db, current_user)
    current_user.pin_hash = hash_pin(payload.new_pin)
    await db.commit()

    access_token, refresh_token = await issue_session_tokens(db, current_user)
    return SessionResponse(
        access_token=access_token, refresh_token=refresh_token, user=current_user
    )


@router.post("/token/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    payload: TokenRefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenRefreshResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    if (
        stored is None
        or stored.revoked_at is not None
        or stored.expires_at < utcnow()
    ):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")

    stored.revoked_at = utcnow()

    user = (await db.execute(select(User).where(User.id == stored.user_id))).scalar_one_or_none()
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "Session expired. Please log in again.")

    access_token, new_refresh_token = await issue_session_tokens(db, user)
    return TokenRefreshResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash, RefreshToken.user_id == current_user.id
        )
    )
    stored = result.scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = utcnow()
        await db.commit()
