import secrets
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


def _generate_prescription_id() -> str:
    return f"PR{secrets.token_hex(4).upper()}"


def _generate_medication_id() -> str:
    return f"med_{secrets.token_hex(8)}"


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_prescription_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    medications: Mapped[list["Medication"]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        order_by="Medication.position",
    )


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_medication_id)
    prescription_id: Mapped[str] = mapped_column(
        ForeignKey("prescriptions.id"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    dosage: Mapped[str] = mapped_column(String, nullable=False)
    dosage_unit: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    dose_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notification_days: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    frequency: Mapped[str] = mapped_column(String, nullable=False)
    times: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    start_from: Mapped[str] = mapped_column(String, nullable=False)
    end_on: Mapped[str] = mapped_column(String, nullable=False)

    prescription: Mapped["Prescription"] = relationship(back_populates="medications")
