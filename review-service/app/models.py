from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base


class Review(Base):
    __tablename__ = "reviews"

    __table_args__ = (
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="check_rating_between_1_and_5",
        ),
        CheckConstraint(
            "status IN ('Pending', 'Approved', 'Rejected')",
            name="check_review_status",
        ),
        UniqueConstraint(
            "user_id",
            "product_id",
            name="unique_user_product_review",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    rating = Column(
        Integer,
        nullable=False,
    )

    title = Column(
        String(150),
        nullable=False,
    )

    comment = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
        default="Pending",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )