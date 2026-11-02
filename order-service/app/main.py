from decimal import Decimal
from uuid import uuid4
import os

import httpx

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Order, OrderItem
from .schemas import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
)
from .security import (
    get_current_user,
    get_user_or_internal_service,
    require_admin_or_internal_service,
)


# --------------------------------------------------
# Service addresses
# --------------------------------------------------

PRODUCT_SERVICE_URL = "http://127.0.0.1:8002"
INVENTORY_SERVICE_URL = "http://127.0.0.1:8003"

# Internal authentication token used for Inventory requests.
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN")


def get_internal_service_headers() -> dict:
    """Build authentication headers for internal service requests."""

    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="INTERNAL_SERVICE_TOKEN is not configured.",
        )

    return {
        "X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN
    }


# --------------------------------------------------
# Initialize database and FastAPI
# --------------------------------------------------

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Order Management Service",
    description="Create orders and manage order status.",
    version="1.1.0",
)


# --------------------------------------------------
# Home and health endpoints
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Order Management Service is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


# --------------------------------------------------
# Get product details from Product service
# --------------------------------------------------

def get_product(product_id: int) -> dict:
    try:
        response = httpx.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=5.0,
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Product Catalog Service is unavailable.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} was not found.",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve product information.",
        )

    return response.json()


# --------------------------------------------------
# Reserve inventory
# --------------------------------------------------

def reserve_inventory(
    product_id: int,
    quantity: int,
    order_number: str,
    user_id: int,
) -> dict:
    try:
        response = httpx.post(
            f"{INVENTORY_SERVICE_URL}/inventory/reservations",
            headers=get_internal_service_headers(),
            json={
                "product_id": product_id,
                "quantity": quantity,
                "order_reference": order_number,
                "requested_by": str(user_id),
            },
            timeout=5.0,
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Inventory Service is unavailable.",
        )

    if response.status_code == 409:
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient stock for product {product_id}.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No inventory record exists for product {product_id}."
            ),
        )

    if not response.is_success:
        raise HTTPException(
            status_code=503,
            detail="Could not reserve product inventory.",
        )

    return response.json()


# --------------------------------------------------
# Release inventory reservation
# --------------------------------------------------

def release_inventory_reservation(reservation_id: int) -> bool:
    try:
        response = httpx.post(
            f"{INVENTORY_SERVICE_URL}/inventory/reservations/"
            f"{reservation_id}/release",
            headers=get_internal_service_headers(),
            timeout=5.0,
        )

        return response.is_success

    except httpx.RequestError:
        return False


# --------------------------------------------------
# Create an order
# Requires authentication
# --------------------------------------------------

@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Obtain the user ID from the verified JWT.
    user_id = current_user["user_id"]

    # Reject duplicate product IDs in the same order.
    product_ids = [item.product_id for item in data.items]

    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=422,
            detail="Each product must appear only once in an order.",
        )

    order_number = f"ORD-{uuid4().hex[:12].upper()}"

    prepared_items = []
    reservations = []

    subtotal = Decimal("0.00")

    try:
        # Retrieve current product prices.
        for item in data.items:
            product = get_product(item.product_id)

            price = Decimal(str(product["price"]))

            if price <= 0:
                raise HTTPException(
                    status_code=422,
                    detail="The product has an invalid price.",
                )

            line_total = price * item.quantity

            prepared_items.append(
                {
                    "product_id": item.product_id,
                    "product_name": product["name"],
                    "quantity": item.quantity,
                    "unit_price": price,
                    "line_total": line_total,
                }
            )

            subtotal += line_total

        # Reserve stock for each product.
        for item in prepared_items:
            reservation = reserve_inventory(
                product_id=item["product_id"],
                quantity=item["quantity"],
                order_number=order_number,
                user_id=user_id,
            )

            reservation_id = reservation["id"]

            item["inventory_reservation_id"] = reservation_id

            reservations.append(reservation_id)

    except HTTPException:
        # Release earlier reservations if a later operation fails.
        for reservation_id in reservations:
            release_inventory_reservation(reservation_id)

        raise

    # Tax, shipping, and discount are initially zero.
    tax_amount = Decimal("0.00")
    shipping_amount = Decimal("0.00")
    discount_amount = Decimal("0.00")

    total_amount = (
        subtotal
        + tax_amount
        + shipping_amount
        - discount_amount
    )

    # Create the order in the Order service database.
    order = Order(
        order_number=order_number,
        user_id=user_id,
        status="Pending",
        subtotal=subtotal,
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        items=[
            OrderItem(**item)
            for item in prepared_items
        ],
    )

    try:
        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    except Exception:
        db.rollback()

        # Release reservations if saving the order fails.
        for reservation_id in reservations:
            release_inventory_reservation(reservation_id)

        raise HTTPException(
            status_code=500,
            detail="Order creation failed. Please try again.",
        )


# --------------------------------------------------
# List all orders
# Administrator or internal service only
# --------------------------------------------------

@app.get(
    "/orders",
    response_model=list[OrderResponse],
)
def get_all_orders(
    principal: dict = Depends(
        require_admin_or_internal_service
    ),
    db: Session = Depends(get_db),
):
    return (
        db.query(Order)
        .order_by(Order.id.desc())
        .all()
    )


# --------------------------------------------------
# Get orders belonging to the authenticated user
# --------------------------------------------------

@app.get(
    "/orders/my-orders",
    response_model=list[OrderResponse],
)
def get_my_orders(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    return (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .all()
    )


# --------------------------------------------------
# Get individual order details
# Owner, Administrator, or internal service
# --------------------------------------------------

@app.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: int,
    principal: dict = Depends(
        get_user_or_internal_service
    ),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    # Customers can view only their own orders.
    if (
        not principal["service"]
        and principal["role"] != "Administrator"
        and order.user_id != principal["user_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to access this order.",
        )

    return order


# --------------------------------------------------
# Update order status
# Administrator or internal service only
# --------------------------------------------------

@app.patch(
    "/orders/{order_id}/status",
    response_model=OrderResponse,
)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    principal: dict = Depends(
        require_admin_or_internal_service
    ),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    allowed_transitions = {
        "Pending": ["Confirmed"],
        "Confirmed": ["Processing"],
        "Processing": ["Shipped"],
        "Shipped": ["Delivered"],
        "Delivered": [],
        "Cancelled": [],
    }

    if data.status not in allowed_transitions.get(
        order.status, []
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot change order status from "
                f"{order.status} to {data.status}."
            ),
        )

    order.status = data.status

    db.commit()
    db.refresh(order)

    return order


# --------------------------------------------------
# Cancel an order
# Owner or Administrator only
# --------------------------------------------------

@app.post(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
)
def cancel_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    # Customers can cancel only their own orders.
    if (
        current_user["role"] != "Administrator"
        and order.user_id != current_user["user_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to cancel this order.",
        )

    if order.status in [
        "Shipped",
        "Delivered",
        "Cancelled",
    ]:
        raise HTTPException(
            status_code=409,
            detail="This order cannot be cancelled.",
        )

    # Release active reservations before cancellation.
    for item in order.items:
        if item.inventory_reservation_id is None:
            continue

        success = release_inventory_reservation(
            item.inventory_reservation_id
        )

        if not success:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Could not release inventory reservation. "
                    "The order has not been marked as cancelled."
                ),
            )

    order.status = "Cancelled"

    db.commit()
    db.refresh(order)

    return order