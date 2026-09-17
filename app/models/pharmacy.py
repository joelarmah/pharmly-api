from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from app.core.ids import generate_id
from app.core.time import utcnow
from app.db.base import Base


class MedicationCatalog(Base):
    """Own the drug data (PRD §5.6's data model, pulled forward as pricing's
    foundation -- the §5.6 endpoints themselves are a separate future PR).
    """

    __tablename__ = "medication_catalog"
    __table_args__ = (
        UniqueConstraint("name", "dosage", "unit", name="uq_medication_catalog_name_dosage_unit"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    dosage: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    form: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    __table_args__ = (UniqueConstraint("name", name="uq_pharmacies_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    # How this pharmacy's prices get populated. "manual" (admin-panel entry)
    # is the only implemented path today; "partner_api" is reserved for a
    # real integration once one exists -- see PRD §5.3/§9.
    inventory_source: Mapped[str] = mapped_column(String, nullable=False, default="manual")


class PharmacyPrice(Base):
    """The local cache pricing is actually read from -- never a live
    partner call. `source`/`synced_at` track provenance and freshness;
    `scripts/seed_pricing_data.py` (see there) is still the only populated
    source today ("seed"), alongside hand-edits via the admin panel
    ("manual"). "partner_api" is reserved for a real integration -- PRD
    §9 open question #4.
    """

    __tablename__ = "pharmacy_prices"

    pharmacy_id: Mapped[str] = mapped_column(
        ForeignKey("pharmacies.id"), primary_key=True, index=True
    )
    catalog_id: Mapped[str] = mapped_column(
        ForeignKey("medication_catalog.id"), primary_key=True, index=True
    )
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    synced_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, nullable=False)
