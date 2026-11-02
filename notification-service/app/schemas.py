from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    user_id: int = Field(gt=0)

    title: str = Field(min_length=1, max_length=150)

    message: str = Field(min_length=1, max_length=2000)

    notification_type: str = Field(
        min_length=1,
        max_length=50,
    )

    event_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    message: str
    notification_type: str
    status: str
    event_id: str | None
    created_at: datetime