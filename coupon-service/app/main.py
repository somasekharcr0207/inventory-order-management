from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import re

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Coupon, CouponRedemption
from .schemas import (
    CouponCreate,
    CouponResponse,
    CouponRedemptionResponse,
    CouponValidationRequest,
    CouponValidationResponse,
)


# Create database tables
Base.metadata.create_all(bind=engine)


# Create FastAPI application
app = FastAPI(
    title="Coupon and Discount Service",
    description="Create coupons, validate discounts, and record redemptions.",
    version="1.0.0",
)


# Use UTC without timezone information for SQLite comparisons.
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


def money(value: Decimal) -> Decimal:
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def find_coupon(db: Session, code: str):
    normalized_code = code.strip().upper()

    return (
        db.query(Coupon)
        .filter(Coupon.code == normalized_code)
        .first()
    )


def evaluate_coupon(
    db: Session,
    data: CouponValidationRequest,
):
    coupon = find_coupon(db, data.code)

    if coupon is None:
        raise HTTPException(
            status_code=404,
            detail="Coupon not found.",
        )

    if not coupon.is_active:
        raise HTTPException(
            status_code=400,
            detail="This coupon is inactive.",
        )

    if normalize_datetime(coupon.expires_at) <= utc_now():
        raise HTTPException(
            status_code=400,
            detail="This coupon has expired.",
        )

    if (
        coupon.usage_limit is not None
        and coupon.usage_count >= coupon.usage_limit
    ):
        raise HTTPException(
            status_code=400,
            detail="This coupon has reached its usage limit.",
        )

    if data.subtotal < coupon.minimum_purchase:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Minimum purchase required is "
                f"{coupon.minimum_purchase}."
            ),
        )

    # Do not allow the same customer to redeem the same coupon
    # repeatedly for the same order.
    existing_redemption = (
        db.query(CouponRedemption)
        .filter(
            CouponRedemption.coupon_id == coupon.id,
            CouponRedemption.user_id == data.user_id,
            CouponRedemption.order_id == data.order_id,
        )
        .first()
    )

    if existing_redemption:
        raise HTTPException(
            status_code=409,
            detail="This coupon has already been redeemed for this order.",
        )

    # Calculate the discount on the backend.
    if coupon.discount_type == "percentage":
        discount = (
            data.subtotal
            * coupon.discount_value
            / Decimal("100")
        )
    else:
        discount = coupon.discount_value

    # A discount cannot exceed the purchase amount.
    discount = min(discount, data.subtotal)
    discount = money(discount)

    total_after_discount = money(
        data.subtotal - discount
    )

    return coupon, discount, total_after_discount


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Coupon and Discount Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Create a coupon
@app.post(
    "/coupons",
    response_model=CouponResponse,
    status_code=201,
)
def create_coupon(
    data: CouponCreate,
    db: Session = Depends(get_db),
):
    code = data.code.strip().upper()

    if not re.fullmatch(r"[A-Z0-9_-]{3,50}", code):
        raise HTTPException(
            status_code=422,
            detail=(
                "Coupon code must contain only letters, numbers, "
                "hyphens, or underscores."
            ),
        )

    if (
        data.discount_type == "percentage"
        and data.discount_value > Decimal("100")
    ):
        raise HTTPException(
            status_code=422,
            detail="Percentage discount cannot exceed 100.",
        )

    expires_at = normalize_datetime(data.expires_at)

    if expires_at <= utc_now():
        raise HTTPException(
            status_code=422,
            detail="Expiration date must be in the future.",
        )

    existing = find_coupon(db, code)

    if existing:
        raise HTTPException(
            status_code=409,
            detail="A coupon with this code already exists.",
        )

    coupon = Coupon(
        code=code,
        description=data.description,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        minimum_purchase=data.minimum_purchase,
        usage_limit=data.usage_limit,
        usage_count=0,
        expires_at=expires_at,
        is_active=1 if data.is_active else 0,
    )

    db.add(coupon)
    db.commit()
    db.refresh(coupon)

    return coupon


# List coupons
@app.get("/coupons", response_model=list[CouponResponse])
def get_coupons(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(Coupon)

    if active_only:
        query = query.filter(Coupon.is_active == 1)

    return query.order_by(Coupon.id.desc()).all()


# Validate a coupon without redeeming it
@app.post(
    "/coupons/validate",
    response_model=CouponValidationResponse,
)
def validate_coupon(
    data: CouponValidationRequest,
    db: Session = Depends(get_db),
):
    coupon, discount, final_total = evaluate_coupon(db, data)

    return {
        "valid": True,
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "subtotal": money(data.subtotal),
        "discount_amount": discount,
        "total_after_discount": final_total,
        "message": "Coupon is valid.",
    }


# Redeem a coupon and record its use
@app.post(
    "/coupons/redeem",
    response_model=CouponRedemptionResponse,
    status_code=201,
)
def redeem_coupon(
    data: CouponValidationRequest,
    db: Session = Depends(get_db),
):
    coupon = find_coupon(db, data.code)

    if coupon is None:
        raise HTTPException(
            status_code=404,
            detail="Coupon not found.",
        )

    # Repeating the same redemption request returns the existing
    # record instead of increasing usage_count again.
    previous_redemption = (
        db.query(CouponRedemption)
        .filter(
            CouponRedemption.coupon_id == coupon.id,
            CouponRedemption.user_id == data.user_id,
            CouponRedemption.order_id == data.order_id,
        )
        .first()
    )

    if previous_redemption:
        return previous_redemption

    coupon, discount, _ = evaluate_coupon(db, data)

    redemption = CouponRedemption(
        coupon_id=coupon.id,
        user_id=data.user_id,
        order_id=data.order_id,
        discount_amount=discount,
    )

    coupon.usage_count += 1

    db.add(redemption)

    try:
        db.commit()
        db.refresh(redemption)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not record the coupon redemption.",
        )

    return redemption


# Get redemption history for a coupon
@app.get(
    "/coupons/{coupon_id}/redemptions",
    response_model=list[CouponRedemptionResponse],
)
def get_coupon_redemptions(
    coupon_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    coupon = db.query(Coupon).filter(
        Coupon.id == coupon_id
    ).first()

    if coupon is None:
        raise HTTPException(
            status_code=404,
            detail="Coupon not found.",
        )

    return (
        db.query(CouponRedemption)
        .filter(CouponRedemption.coupon_id == coupon_id)
        .order_by(CouponRedemption.id.desc())
        .limit(limit)
        .all()
    )


# Deactivate a coupon
@app.patch("/coupons/{coupon_id}/deactivate")
def deactivate_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
):
    coupon = db.query(Coupon).filter(
        Coupon.id == coupon_id
    ).first()

    if coupon is None:
        raise HTTPException(
            status_code=404,
            detail="Coupon not found.",
        )

    coupon.is_active = 0
    db.commit()

    return {
        "message": "Coupon deactivated successfully.",
        "coupon_id": coupon.id,
        "is_active": False,
    }