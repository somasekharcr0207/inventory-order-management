from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
)

from .database import Base


class InventoryItem(Base):
    __tablename__ = "inventory"

    __table_args__ = (
        CheckConstraint(
            "quantity_on_hand >= 0",
            name="check_nonnegative_stock",
        ),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="check_nonnegative_reserved",
        ),
        CheckConstraint(
            "reserved_quantity <= quantity_on_hand",
            name="check_reserved_not_above_stock",
        ),
        CheckConstraint(
            "low_stock_threshold >= 0",
            name="check_nonnegative_threshold",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    product_id = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
    )

    quantity_on_hand = Column(
        Integer,
        nullable=False,
        default=0,
    )

    reserved_quantity = Column(
        Integer,
        nullable=False,
        default=0,
    )

    low_stock_threshold = Column(
        Integer,
        nullable=False,
        default=5,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    quantity_change = Column(
        Integer,
        nullable=False,
    )

    reason = Column(
        String(250),
        nullable=False,
    )

    responsible_user = Column(
        String(100),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    
class StockReservation(Base):
    __tablename__ = "stock_reservations"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_reservation_quantity_positive",
        ),
        CheckConstraint(
            "status IN ('active', 'released', 'consumed')",
            name="check_reservation_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
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

    status = Column(
        String(20),
        nullable=False,
        default="active",
    )

    order_reference = Column(
        String(100),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )    