from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserOut

PHONE_PATTERN = r"^\+[1-9]\d{6,14}$"
PIN_PATTERN = r"^\d{6}$"


class OtpRequest(BaseModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)


class OtpVerifyRequest(BaseModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    code: str = Field(pattern=r"^\d{6}$")


class OtpVerifyResponse(BaseModel):
    verification_token: str


class RegisterRequest(BaseModel):
    verification_token: str
    phone_number: str = Field(pattern=PHONE_PATTERN)
    full_name: str = Field(min_length=1)
    email: str | None = None
    pin: str = Field(pattern=PIN_PATTERN)


class PinResetRequest(BaseModel):
    verification_token: str
    phone_number: str | None = Field(default=None, pattern=PHONE_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)


class LoginRequest(BaseModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)


class PinVerifyRequest(BaseModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    pin: str = Field(pattern=PIN_PATTERN)


class PinChangeRequest(BaseModel):
    phone_number: str = Field(pattern=PHONE_PATTERN)
    current_pin: str = Field(pattern=PIN_PATTERN)
    new_pin: str = Field(pattern=PIN_PATTERN)

    @field_validator("new_pin")
    @classmethod
    def new_pin_must_differ(cls, v: str, info):
        if v == info.data.get("current_pin"):
            raise ValueError("new PIN must differ from current PIN")
        return v


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut
