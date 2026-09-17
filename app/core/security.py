import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()


def hash_pin(pin: str) -> str:
    return _ph.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return _ph.verify(pin_hash, pin)
    except VerifyMismatchError:
        return False


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_otp(code: str) -> str:
    return _ph.hash(code)


def verify_otp_code(code: str, code_hash: str) -> bool:
    try:
        return _ph.verify(code_hash, code)
    except VerifyMismatchError:
        return False


def _encode_jwt(payload: dict[str, Any], expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    to_encode = {**payload, "iat": now, "exp": now + expires_delta}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_jwt(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_access_token(user_id: str) -> str:
    return _encode_jwt(
        {"sub": user_id, "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def decode_access_token(token: str) -> str:
    """Returns the user_id (sub). Raises jwt exceptions on invalid/expired tokens."""
    payload = _decode_jwt(token)
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload["sub"]


def create_verification_token(phone_number: str, purpose: Literal["signup", "forgot_pin"]) -> str:
    return _encode_jwt(
        {"sub": phone_number, "type": "verification", "purpose": purpose},
        timedelta(minutes=settings.verification_token_expire_minutes),
    )


def decode_verification_token(
    token: str, expected_purpose: Literal["signup", "forgot_pin"]
) -> str:
    """Returns the phone_number (sub). Raises jwt exceptions on invalid/expired/wrong purpose."""
    payload = _decode_jwt(token)
    if payload.get("type") != "verification":
        raise jwt.InvalidTokenError("not a verification token")
    if payload.get("purpose") != expected_purpose:
        raise jwt.InvalidTokenError("verification token purpose mismatch")
    return payload["sub"]


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_otp_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
