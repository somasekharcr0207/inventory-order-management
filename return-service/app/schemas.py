from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------
# Return item creation
# --------------------------------------------------

class ReturnItemCreate(BaseModel):
    order_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


# --------------------------------------------------
# Return creation
# --------------------------------------------------

class ReturnCreate(BaseModel):
    order_id: int = Field(gt=0)

    reason: str = Field(
        min_length=5,
        max_length=2000,
    )

    items: list[ReturnItemCreate] = Field(min_length=1)


# --------------------------------------------------
# Return status update
# --------------------------------------------------

class ReturnStatusUpdate(BaseModel):
    status: Literal[
        "Approved",
        "Rejected",
        "ItemReceived",
        "Refunded",
        "Cancelled",
    ]


# --------------------------------------------------
# Return item response
# --------------------------------------------------

class ReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_item_id: int
    product_id: int
    quantity: int
    unit_price: Decimal


# --------------------------------------------------
# Refund response
# --------------------------------------------------

class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_request_id: int
    amount: Decimal
    status: str
    refund_reference: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------
# Complete return response
# --------------------------------------------------

class ReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_number: str
    order_id: int
    user_id: int
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime

    items: list[ReturnItemResponse]
    refunds: list[RefundResponse]