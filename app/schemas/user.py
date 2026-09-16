from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    phone_number: str
    full_name: str
    email: str | None
    address: str | None
    avatar_url: str | None
    membership_activated_at: datetime

    @field_serializer("membership_activated_at")
    def _serialize_utc(self, value: datetime) -> str:
        # Stored values are naive and implicitly UTC -- see app.core.time.
        return value.isoformat(timespec="seconds") + "Z"


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    address: str | None = None
