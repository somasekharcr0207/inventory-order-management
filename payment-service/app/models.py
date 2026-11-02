from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
)

from .database import Base


class Payment(Base):
    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="check_payment_amount_positive",
        ),
        CheckConstraint(
            "status IN ('Pending', 'Succeeded', 'Failed', 'Cancelled')",
            name="check_payment_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    payment_reference = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
        default="Pending",
    )

    idempotency_key = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
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