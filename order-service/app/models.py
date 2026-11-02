from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship

from .database import Base


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "total_amount >= 0",
            name="check_order_total_nonnegative",
        ),
        CheckConstraint(
            "status IN ('Pending', 'Confirmed', 'Processing', "
            "'Shipped', 'Delivered', 'Cancelled')",
            name="check_order_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    order_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    status = Column(
        String(20),
        nullable=False,
        default="Pending",
    )

    subtotal = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    tax_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    shipping_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    discount_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    total_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
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
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_order_item_quantity_positive",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="check_order_item_price_nonnegative",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    product_name = Column(
        String(150),
        nullable=False,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False,
    )

    line_total = Column(
        Numeric(10, 2),
        nullable=False,
    )

    inventory_reservation_id = Column(
        Integer,
        nullable=True,
    )

    order = relationship(
        "Order",
        back_populates="items",
    )