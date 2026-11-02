from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=50)

    description: str | None = Field(
        default=None,
        max_length=250,
    )

    discount_type: Literal["percentage", "fixed"]

    discount_value: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )

    minimum_purchase: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
    )

    usage_limit: int | None = Field(
        default=None,
        gt=0,
    )

    expires_at: datetime

    is_active: bool = True


class CouponValidationRequest(BaseModel):
    code: str = Field(min_length=3, max_length=50)

    user_id: int = Field(gt=0)

    order_id: int = Field(gt=0)

    subtotal: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )


class CouponResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None
    discount_type: str
    discount_value: Decimal
    minimum_purchase: Decimal
    usage_limit: int | None
    usage_count: int
    expires_at: datetime
    is_active: bool
    created_at: datetime


class CouponValidationResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str
    subtotal: Decimal
    discount_amount: Decimal
    total_after_discount: Decimal
    message: str


class CouponRedemptionResponse(BaseModel):
    id: int
    coupon_id: int
    user_id: int
    order_id: int
    discount_amount: Decimal
    redeemed_at: datetime