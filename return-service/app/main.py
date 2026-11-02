from uuid import uuid4
from decimal import Decimal
import os

import httpx

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from . import models
from .database import Base, engine, get_db
from .models import ReturnRequest, ReturnItem, RefundRecord

from .schemas import (
    ReturnCreate,
    ReturnResponse,
    ReturnStatusUpdate,
    RefundResponse,
)

from .security import get_current_user, require_admin


# --------------------------------------------------
# Other microservice addresses
# --------------------------------------------------

ORDER_SERVICE_URL = "http://127.0.0.1:8005"
INVENTORY_SERVICE_URL = "http://127.0.0.1:8003"


# Internal authentication token
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN")


def get_internal_service_headers() -> dict:
    """Build internal service authentication headers."""

    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_SERVICE_TOKEN is not configured.",
        )

    return {
        "X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN
    }


# --------------------------------------------------
# Create database tables
# --------------------------------------------------

Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# Create FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="Return and Refund Service",
    description="Manage product returns and simulated refunds.",
    version="1.1.0",
)


# --------------------------------------------------
# Home endpoint
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Return and Refund Service is running",
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
# Retrieve return request and related records
# --------------------------------------------------

def get_return_record(db: Session, return_id: int):
    record = (
        db.query(ReturnRequest)
        .options(
            selectinload(ReturnRequest.items),
            selectinload(ReturnRequest.refunds),
        )
        .filter(ReturnRequest.id == return_id)
        .first()
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found.",
        )

    return record


# --------------------------------------------------
# Verify return ownership
# --------------------------------------------------

def check_return_access(
    record: ReturnRequest,
    current_user: dict,
):
    """Allow the return owner or an Administrator."""

    if current_user["role"] == "Administrator":
        return

    if record.user_id != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this return.",
        )


# --------------------------------------------------
# Submit a return request
# Customer authentication required
# --------------------------------------------------

@app.post(
    "/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return(
    data: ReturnCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Retrieve the order through Order Service.
    order = get_order(data.order_id)

    # Verify order ownership using authenticated JWT.
    if (
        current_user["role"] != "Administrator"
        and order["user_id"] != current_user["user_id"]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This order does not belong to this customer.",
        )

    # Only delivered orders are eligible for returns.
    if order["status"] != "Delivered":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only delivered orders are eligible for returns.",
        )

    order_items = {
        item["id"]: item
        for item in order["items"]
    }

    requested_ids = [
        item.order_item_id
        for item in data.items
    ]

    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each order item can appear only once per request.",
        )

    return_items = []

    # Validate items and prevent excessive returns.
    for requested_item in data.items:

        order_item = order_items.get(
            requested_item.order_item_id
        )

        if order_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Order item {requested_item.order_item_id} "
                    "does not belong to this order."
                ),
            )

        # Find earlier return requests.
        previous_returns = (
            db.query(ReturnItem)
            .join(
                ReturnRequest,
                ReturnItem.return_request_id == ReturnRequest.id,
            )
            .filter(
                ReturnItem.order_item_id
                == requested_item.order_item_id,
                ReturnRequest.status.notin_(
                    ["Rejected", "Cancelled"]
                ),
            )
            .all()
        )

        already_requested = sum(
            item.quantity for item in previous_returns
        )

        purchased_quantity = order_item["quantity"]

        if (
            already_requested + requested_item.quantity
            > purchased_quantity
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Requested return quantity exceeds the "
                    "remaining quantity for this order item."
                ),
            )

        return_items.append(
            ReturnItem(
                order_item_id=order_item["id"],
                product_id=order_item["product_id"],
                quantity=requested_item.quantity,
                unit_price=Decimal(
                    str(order_item["unit_price"])
                ),
            )
        )

    # Generate unique return number.
    return_number = f"RET-{uuid4().hex[:12].upper()}"

    record = ReturnRequest(
        return_number=return_number,
        order_id=data.order_id,
        user_id=order["user_id"],
        reason=data.reason,
        status="Requested",
        items=return_items,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create return request.",
        )

    return get_return_record(db, record.id)


# --------------------------------------------------
# Get returns belonging to authenticated customer
# --------------------------------------------------

@app.get(
    "/returns/my-returns",
    response_model=list[ReturnResponse],
)
def get_my_returns(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(ReturnRequest)
        .options(
            selectinload(ReturnRequest.items),
            selectinload(ReturnRequest.refunds),
        )
        .filter(
            ReturnRequest.user_id == current_user["user_id"]
        )
        .order_by(ReturnRequest.id.desc())
        .all()
    )

    return records


# --------------------------------------------------
# Get one return request
# Owner or Administrator
# --------------------------------------------------

@app.get(
    "/returns/{return_id}",
    response_model=ReturnResponse,
)
def get_return(
    return_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_return_record(db, return_id)

    check_return_access(record, current_user)

    return record


# --------------------------------------------------
# Update return status
# Administrator only
# --------------------------------------------------

@app.patch(
    "/returns/{return_id}/status",
    response_model=ReturnResponse,
)
def update_return_status(
    return_id: int,
    data: ReturnStatusUpdate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = get_return_record(db, return_id)

    allowed_transitions = {
        "Requested": ["Approved", "Rejected", "Cancelled"],
        "Approved": ["ItemReceived", "Cancelled"],
        "ItemReceived": ["Refunded"],
        "Rejected": [],
        "Refunded": [],
        "Cancelled": [],
    }

    if data.status not in allowed_transitions.get(
        record.status, []
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot change return status from "
                f"{record.status} to {data.status}."
            ),
        )

    # Restore stock only after physical receipt and acceptance.
    if data.status == "ItemReceived":

        # Check Inventory Service availability.
        try:
            response = httpx.get(
                f"{INVENTORY_SERVICE_URL}/health",
                timeout=5.0,
            )

        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Inventory Service is unavailable.",
            )

        if not response.is_success:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Inventory Service is unavailable.",
            )

        refund_amount = Decimal("0.00")

        # Restore each accepted returned item.
        for item in record.items:

            try:
                inventory_response = httpx.patch(
                    f"{INVENTORY_SERVICE_URL}/inventory/"
                    f"{item.product_id}/stock",
                    headers=get_internal_service_headers(),
                    json={
                        "action": "add",
                        "quantity": item.quantity,
                        "reason": (
                            f"Accepted return {record.return_number}"
                        ),
                        "responsible_user": "return-service",
                    },
                    timeout=5.0,
                )

            except httpx.RequestError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Inventory could not be updated. "
                        "Manual reconciliation may be required."
                    ),
                )

            if not inventory_response.is_success:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Inventory restoration failed. "
                        "Manual reconciliation may be required."
                    ),
                )

            refund_amount += (
                Decimal(str(item.unit_price))
                * item.quantity
            )

        # Create simulated refund record.
        refund_record = RefundRecord(
            return_request_id=record.id,
            amount=refund_amount,
            status="Pending",
            refund_reference=f"REF-{uuid4().hex[:12].upper()}",
        )

        db.add(refund_record)

    # Mark the simulated refund as processed.
    # This does not transfer real money.
    if data.status == "Refunded":

        if not record.refunds:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No refund record exists for this return.",
            )

        for refund in record.refunds:
            refund.status = "Processed"

    record.status = data.status

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update return status.",
        )

    return get_return_record(db, record.id)


# --------------------------------------------------
# Get refund records for a return
# Owner or Administrator
# --------------------------------------------------

@app.get(
    "/returns/{return_id}/refunds",
    response_model=list[RefundResponse],
)
def get_refunds(
    return_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_return_record(db, return_id)

    check_return_access(record, current_user)

    return record.refunds