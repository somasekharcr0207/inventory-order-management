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

from .database import Base


class Coupon(Base):
    __tablename__ = "coupons"

    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('percentage', 'fixed')",
            name="check_coupon_discount_type",
        ),
        CheckConstraint(
            "discount_value > 0",
            name="check_coupon_discount_positive",
        ),
        CheckConstraint(
            "discount_type != 'percentage' OR discount_value <= 100",
            name="check_coupon_percentage_maximum",
        ),
        CheckConstraint(
            "minimum_purchase >= 0",
            name="check_coupon_minimum_purchase",
        ),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0",
            name="check_coupon_usage_limit",
        ),
        CheckConstraint(
            "usage_count >= 0",
            name="check_coupon_usage_count",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    code = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    description = Column(
        String(250),
        nullable=True,
    )

    discount_type = Column(
        String(20),
        nullable=False,
    )

    discount_value = Column(
        Numeric(10, 2),
        nullable=False,
    )

    minimum_purchase = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    usage_limit = Column(
        Integer,
        nullable=True,
    )

    usage_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
    )

    is_active = Column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    __table_args__ = (
        CheckConstraint(
            "discount_amount > 0",
            name="check_redemption_discount_positive",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    coupon_id = Column(
        Integer,
        ForeignKey("coupons.id"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    discount_amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    redeemed_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )