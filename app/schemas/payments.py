from typing import Literal

from pydantic import BaseModel


class InitializePaymentRequest(BaseModel):
    amount: float
    email: str
    reference: str | None = None


class InitializePaymentResponse(BaseModel):
    reference: str
    checkout_url: str


class VerifyPaymentResponse(BaseModel):
    status: Literal["pending", "success", "failed"]
