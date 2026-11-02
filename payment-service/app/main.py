import os

from uuid import uuid4
from decimal import Decimal

import httpx

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Payment
from .schemas import PaymentCreate, PaymentResponse
from .security import get_current_user


# --------------------------------------------------
# Order Management Service configuration
# --------------------------------------------------

ORDER_SERVICE_URL = "http://127.0.0.1:8005"

# Internal authentication token shared with Order Service.
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN")


def get_internal_service_headers() -> dict:
    """Build authentication headers for Order service requests."""

    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_SERVICE_TOKEN is not configured.",
        )

    return {
        "X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN
    }


# --------------------------------------------------
# Create payment database tables
# --------------------------------------------------

Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# Create FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="Payment Service",
    description="Simulated payment processing for orders.",
    version="1.1.0",
)


# --------------------------------------------------
# Home endpoint
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Payment Service is running",
        "docs": "/docs",
    }


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy"}


# --------------------------------------------------
# Retrieve order from Order Management Service
# --------------------------------------------------

def get_order(order_id: int) -> dict:
    """Retrieve trusted order information using internal authentication."""

    try:
        response = httpx.get(
            f"{ORDER_SERVICE_URL}/orders/{order_id}",
            headers=get_internal_service_headers(),
            timeout=5.0,
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Order Management Service is unavailable.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve order information.",
        )

    return response.json()


# --------------------------------------------------
# Verify order ownership
# --------------------------------------------------

def check_order_access(
    order: dict,
    current_user: dict,
) -> None:
    """Allow the order owner or an Administrator."""

    if current_user["role"] == "Administrator":
        return

    if order.get("user_id") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this payment.",
        )


# --------------------------------------------------
# Create a simulated payment
# Customer authentication required
# --------------------------------------------------

@app.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get trusted order information.
    order = get_order(data.order_id)

    # Verify that the customer owns this order.
    check_order_access(order, current_user)

    # Check whether this request has already been processed.
    existing_payment = (
        db.query(Payment)
        .filter(
            Payment.idempotency_key == data.idempotency_key
        )
        .first()
    )

    if existing_payment:

        if existing_payment.order_id != data.order_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This idempotency key has already been used "
                    "for another order."
                ),
            )

        # Return the existing payment instead of processing again.
        return existing_payment

    # Check order eligibility.
    if order["status"] in [
        "Cancelled",
        "Shipped",
        "Delivered",
    ]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order is not eligible for payment.",
        )

    # Use the total calculated by Order Management Service.
    amount = Decimal(str(order["total_amount"]))

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The order amount must be greater than zero.",
        )

    # Prevent another successful payment for the same order.
    successful_payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == data.order_id,
            Payment.status == "Succeeded",
        )
        .first()
    )

    if successful_payment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order has already been paid.",
        )

    # Determine simulated payment result.
    if data.outcome == "success":
        payment_status = "Succeeded"

    elif data.outcome == "failure":
        payment_status = "Failed"

    else:
        payment_status = "Pending"

    # If payment succeeds, confirm an order that is still pending.
    if (
        payment_status == "Succeeded"
        and order["status"] == "Pending"
    ):
        try:
            order_response = httpx.patch(
                f"{ORDER_SERVICE_URL}/orders/{data.order_id}/status",
                headers=get_internal_service_headers(),
                json={"status": "Confirmed"},
                timeout=5.0,
            )

        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Could not contact the Order Management Service."
                ),
            )

        if not order_response.is_success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Payment confirmation could not update the order."
                ),
            )

    # Create payment record.
    payment = Payment(
        payment_reference=f"PAY-{uuid4().hex[:12].upper()}",
        order_id=data.order_id,
        amount=amount,
        status=payment_status,
        idempotency_key=data.idempotency_key,
    )

    db.add(payment)

    try:
        db.commit()
        db.refresh(payment)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the payment record.",
        )

    return payment


# --------------------------------------------------
# Get payment details
# Customer authentication required
# --------------------------------------------------

@app.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
)
def get_payment(
    payment_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    # Retrieve order information for ownership verification.
    order = get_order(payment.order_id)

    check_order_access(order, current_user)

    return payment


# --------------------------------------------------
# Cancel a pending simulated payment
# Customer authentication required
# --------------------------------------------------

@app.post(
    "/payments/{payment_id}/cancel",
    response_model=PaymentResponse,
)
def cancel_payment(
    payment_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    # Verify ownership through Order Management Service.
    order = get_order(payment.order_id)

    check_order_access(order, current_user)

    if payment.status != "Pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending payments can be cancelled.",
        )

    payment.status = "Cancelled"

    try:
        db.commit()
        db.refresh(payment)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not cancel the payment.",
        )

    return payment