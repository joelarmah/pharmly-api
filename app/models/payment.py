from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.core.time import utcnow
from app.db.base import Base
from app.models.order import Order


class PaymentTransaction(Base):
    """A Paystack transaction session -- created by initialize_payment,
    kept current by verify_payment (client polling, cached briefly) and
    handle_webhook (Paystack's own callback, the actual source of truth).
    order_id stays null until order_service.place_order links it.
    """

    __tablename__ = "payment_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    reference: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # ondelete="CASCADE" here too, same reasoning as Order.prescription_id --
    # user_id and (transitively) order_id both cascade independently from a
    # User delete, with no guaranteed ordering between the paths.
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # GHS major units, matching Order.total's convention -- the pesewas
    # (x100) conversion happens only when actually calling Paystack.
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    paystack_raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
    # Drives verify_payment's cache window -- null until the first verify.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # One-directional, no back_populates -- purely for admin display, same
    # reasoning as Order.pharmacy/Order.prescription.
    order: Mapped[Order | None] = relationship()

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"
