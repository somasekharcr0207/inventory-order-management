from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('Requested', 'Approved', 'Rejected', "
            "'ItemReceived', 'Refunded', 'Cancelled')",
            name="check_return_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    return_number = Column(
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

    user_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    reason = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String(30),
        nullable=False,
        default="Requested",
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

    items = relationship(
        "ReturnItem",
        back_populates="return_request",
        cascade="all, delete-orphan",
    )

    refunds = relationship(
        "RefundRecord",
        back_populates="return_request",
        cascade="all, delete-orphan",
    )


class ReturnItem(Base):
    __tablename__ = "return_items"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_return_quantity_positive",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="check_return_price_nonnegative",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    return_request_id = Column(
        Integer,
        ForeignKey("return_requests.id"),
        nullable=False,
        index=True,
    )

    order_item_id = Column(
        Integer,
        nullable=False,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False,
    )

    return_request = relationship(
        "ReturnRequest",
        back_populates="items",
    )


class RefundRecord(Base):
    __tablename__ = "refund_records"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="check_refund_amount_nonnegative",
        ),
        CheckConstraint(
            "status IN ('Pending', 'Processed', 'Failed')",
            name="check_refund_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    return_request_id = Column(
        Integer,
        ForeignKey("return_requests.id"),
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

    refund_reference = Column(
        String(100),
        unique=True,
        nullable=False,
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

    return_request = relationship(
        "ReturnRequest",
        back_populates="refunds",
    )