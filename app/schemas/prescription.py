from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class MedicationIn(BaseModel):
    id: str  # client-generated; the server assigns its own id (PRD §5.2)
    name: str
    dosage: str
    dosage_unit: str
    quantity: int
    quantity_unit: str
    type: str
    dose_amount: int
    duration_days: int
    reminder_enabled: bool
    notification_days: list[str]
    frequency: str
    times: list[str]
    start_from: str
    end_on: str


class MedicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    dosage: str
    dosage_unit: str
    quantity: int
    quantity_unit: str
    type: str
    dose_amount: int
    duration_days: int
    reminder_enabled: bool
    notification_days: list[str]
    frequency: str
    times: list[str]
    start_from: str
    end_on: str


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    medications: list[MedicationOut]
    image_url: str | None
    status: str
    submitted_at: datetime

    @field_serializer("submitted_at")
    def _serialize_utc(self, value: datetime) -> str:
        # Stored values are naive and implicitly UTC -- see app.core.time.
        return value.isoformat(timespec="seconds") + "Z"
