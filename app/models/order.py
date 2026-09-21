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
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # ondelete="CASCADE" here too (not just on user_id) -- prescriptions.
    # user_id and orders.user_id both cascade independently from a User
    # delete, with no guaranteed ordering between the two cascade paths;
    # without this, Postgres could delete the prescription before the
    # order that references it and raise a FK violation anyway. An order
    # can't outlive its prescription regardless of *why* it's being
    # deleted, so this is the correct constraint on its own merits too.
    prescription_id: Mapped[str] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    pharmacy_id: Mapped[str] = mapped_column(
        ForeignKey("pharmacies.id"), index=True, nullable=False
    )
    payment_type: Mapped[str] = mapped_column(String, nullable=False)
    # For card/mobileMoney, order_service.place_order verifies this against
    # a successful PaymentTransaction (amount-checked too) before accepting
    # the order -- see app/services/payment_service.py.
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
