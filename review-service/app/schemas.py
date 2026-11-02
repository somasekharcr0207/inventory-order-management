from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class ReviewCreate(BaseModel):
    user_id: int = Field(gt=0)
    product_id: int = Field(gt=0)

    rating: int = Field(ge=1, le=5)

    title: str = Field(min_length=3, max_length=150)

    comment: str = Field(min_length=5, max_length=2000)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)

    title: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
    )

    comment: str | None = Field(
        default=None,
        min_length=5,
        max_length=2000,
    )


class ReviewStatusUpdate(BaseModel):
    status: Literal["Pending", "Approved", "Rejected"]


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    rating: int
    title: str
    comment: str
    status: str
    created_at: datetime
    updated_at: datetime


class ReviewSummaryResponse(BaseModel):
    product_id: int
    average_rating: float | None
    review_count: int