from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_on_hand: int
    reserved_quantity: int
    low_stock_threshold: int
    updated_at: datetime

    @property
    def available_quantity(self) -> int:
        return self.quantity_on_hand - self.reserved_quantity


class StockAdjustment(BaseModel):
    action: Literal["add", "deduct", "set"]

    quantity: int = Field(ge=0)

    reason: str = Field(min_length=3, max_length=250)

    responsible_user: str | None = Field(
        default=None,
        max_length=100,
    )

    low_stock_threshold: int | None = Field(
        default=None,
        ge=0,
    )


class ReservationCreate(BaseModel):
    product_id: int = Field(gt=0)

    quantity: int = Field(gt=0)

    order_reference: str | None = Field(
        default=None,
        max_length=100,
    )

    requested_by: str | None = Field(
        default=None,
        max_length=100,
    )


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    status: str
    order_reference: str | None
    created_at: datetime


class InventoryTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_change: int
    reason: str
    responsible_user: str | None
    created_at: datetime