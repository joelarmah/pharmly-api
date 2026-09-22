from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.ids import generate_id
from app.db.base import Base


class PhoneLookupAttempt(Base):
    __tablename__ = "phone_lookup_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    phone_number: Mapped[str] = mapped_column(String, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )
