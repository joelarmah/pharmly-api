from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.core.time import utcnow
from app.db.base import Base
from app.models.pharmacy import Pharmacy
from app.models.prescription import Prescription


class Order(Base):
    """A prescription can only ever produce one order -- the unique
    constraint on prescription_id is both the idempotency mechanism for
    POST /orders (a retry returns the existing row) and a real business
    rule (a script gets filled once). See PRD §5.4/§9.
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    prescription_id: Mapped[str] = mapped_column(
        ForeignKey("prescriptions.id"), unique=True, index=True, nullable=False
    )
    pharmacy_id: Mapped[str] = mapped_column(
        ForeignKey("pharmacies.id"), index=True, nullable=False
    )
    payment_type: Mapped[str] = mapped_column(String, nullable=False)
    # Accepted/stored as given for card/mobileMoney -- not yet verified
    # against Paystack (PRD §5.5, not built yet). Flagged, not silently
    # trusted.
    payment_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    progress: Mapped[str] = mapped_column(String, nullable=False, default="preparing")
    # Computed server-side from PharmacyProduct prices at placement time --
    # never trusted from the client.
    total: Mapped[float] = mapped_column(Float, nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)

    pharmacy: Mapped[Pharmacy] = relationship()
    # One-directional, no back_populates -- purely so items_label can be
    # built from the prescription's medications without denormalizing it
    # onto Order itself.
    prescription: Mapped[Prescription] = relationship()

    def __str__(self) -> str:
        return f"{self.id} ({self.progress})"
