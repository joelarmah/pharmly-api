from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlaceOrderRequest(BaseModel):
    prescription_id: str
    pharmacy_id: str
    payment_type: Literal["cashOnDelivery", "card", "mobileMoney"]
    # For card/mobileMoney -- accepted and stored as given, not yet verified
    # against Paystack (PRD §5.5, not built yet).
    payment_reference: str | None = None


class PlaceOrderResponse(BaseModel):
    order_id: str


class OrderOut(BaseModel):
    id: str
    pharmacy_name: str
    items_label: str
    progress: Literal["preparing", "onTheWay", "delivered"]
    # PRD's date_label (a pre-formatted display string) is replaced with a
    # raw timestamp -- PRD §9 open question #5, resolved this way since the
    # mock's ETA-dependent strings (e.g. "Arrives Jul 7, by 11:15 AM") need
    # delivery-ETA data this backend doesn't track.
    placed_at: datetime
    total: float
