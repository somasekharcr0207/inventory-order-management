from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Notification
from .schemas import NotificationCreate, NotificationResponse


# Create the notification database tables
Base.metadata.create_all(bind=engine)


# Create the FastAPI application
app = FastAPI(
    title="Notification Service",
    description="Manage customer and administrator notifications.",
    version="1.0.0",
)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Notification Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Create a notification
@app.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=201,
)
def create_notification(
    data: NotificationCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    # Avoid creating a duplicate notification for the same event.
    if data.event_id:
        existing = (
            db.query(Notification)
            .filter(Notification.event_id == data.event_id)
            .first()
        )

        if existing:
            if (
                existing.user_id != data.user_id
                or existing.notification_type != data.notification_type
                or existing.title != data.title
                or existing.message != data.message
            ):
                raise HTTPException(
                    status_code=409,
                    detail="This event ID was used for a different notification.",
                )

            response.status_code = 200
            return existing

    notification = Notification(
        user_id=data.user_id,
        title=data.title,
        message=data.message,
        notification_type=data.notification_type,
        event_id=data.event_id,
        status="unread",
    )

    db.add(notification)

    try:
        db.commit()
        db.refresh(notification)

    except IntegrityError:
        db.rollback()

        # Another request may have created the same event simultaneously.
        if data.event_id:
            existing = (
                db.query(Notification)
                .filter(Notification.event_id == data.event_id)
                .first()
            )

            if existing:
                if (
                    existing.user_id == data.user_id
                    and existing.notification_type == data.notification_type
                    and existing.title == data.title
                    and existing.message == data.message
                ):
                    response.status_code = 200
                    return existing

                raise HTTPException(
                    status_code=409,
                    detail="This event ID was used for a different notification.",
                )

        raise HTTPException(
            status_code=409,
            detail="Could not create the notification because of a database conflict.",
        )

    return notification


# Get notifications for a user
@app.get(
    "/notifications",
    response_model=list[NotificationResponse],
)
def get_notifications(
    user_id: int = Query(gt=0),
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(
        Notification.user_id == user_id
    )

    if unread_only:
        query = query.filter(Notification.status == "unread")

    return (
        query.order_by(Notification.id.desc())
        .limit(limit)
        .all()
    )


# Mark a notification as read
@app.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found.",
        )

    notification.status = "read"

    db.commit()
    db.refresh(notification)

    return notification


# Delete a notification
@app.delete(
    "/notifications/{notification_id}",
    status_code=204,
)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found.",
        )

    db.delete(notification)
    db.commit()

    return Response(status_code=204)