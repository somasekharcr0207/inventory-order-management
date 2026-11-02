from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from datetime import datetime
from decimal import Decimal


class PaymentCreate(BaseModel):
    order_id: int = Field(gt=0)

    idempotency_key: str = Field(
        min_length=5,
        max_length=100,
    )

    outcome: Literal["success", "failure", "pending"] = "success"


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_reference: str
    order_id: int
    amount: Decimal
    status: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime