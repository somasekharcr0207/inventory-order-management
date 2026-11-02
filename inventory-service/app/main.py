from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import (
    InventoryItem,
    InventoryTransaction,
    StockReservation,
)
from .schemas import (
    InventoryResponse,
    InventoryTransactionResponse,
    ReservationCreate,
    ReservationResponse,
    StockAdjustment,
)
from .security import get_user_or_internal_service


# Create the database tables.
Base.metadata.create_all(bind=engine)


# Create the FastAPI application.
app = FastAPI(
    title="Inventory Management Service",
    description="Manage stock, reservations, and inventory transactions.",
    version="1.1.0",
)


# --------------------------------------------------
# Home endpoint
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Inventory Management Service is running",
        "docs": "/docs",
    }


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy"}


# --------------------------------------------------
# Get all inventory records
# --------------------------------------------------

@app.get("/inventory", response_model=list[InventoryResponse])
def get_all_inventory(
    db: Session = Depends(get_db),
):
    return (
        db.query(InventoryItem)
        .order_by(InventoryItem.product_id.asc())
        .all()
    )


# --------------------------------------------------
# Get inventory for one product
# --------------------------------------------------

@app.get(
    "/inventory/{product_id}",
    response_model=InventoryResponse,
)
def get_product_inventory(
    product_id: int,
    db: Session = Depends(get_db),
):
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.product_id == product_id)
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found for this product.",
        )

    return item


# --------------------------------------------------
# Add, deduct, or set stock
#
# Administrator / Inventory Manager:
#   May perform normal stock adjustments.
#
# Trusted internal Returns service:
#   May only add returned stock.
# --------------------------------------------------

@app.patch(
    "/inventory/{product_id}/stock",
    response_model=InventoryResponse,
)
def adjust_stock(
    product_id: int,
    data: StockAdjustment,
    current_user: dict = Depends(get_user_or_internal_service),
    db: Session = Depends(get_db),
):
    # Check authorization before modifying inventory.
    if current_user.get("service"):

        # Internal services may only add returned stock.
        if data.action != "add":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Internal service can only add returned stock."
                ),
            )

        # Internal services cannot change stock thresholds.
        if data.low_stock_threshold is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Internal service cannot change the low-stock threshold."
                ),
            )

    elif current_user["role"] not in {
        "Administrator",
        "Inventory Manager",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Administrator or Inventory Manager permission "
                "is required."
            ),
        )

    # Add and deduct operations require a positive quantity.
    if data.action in ("add", "deduct") and data.quantity == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Quantity must be greater than zero for add or deduct."
            ),
        )

    # Find the existing inventory record.
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.product_id == product_id)
        .first()
    )

    # Create an inventory record if this product has no stock record.
    if item is None:
        item = InventoryItem(
            product_id=product_id,
            quantity_on_hand=0,
            reserved_quantity=0,
            low_stock_threshold=5,
        )

        db.add(item)
        db.flush()

    previous_quantity = item.quantity_on_hand

    # Add stock.
    if data.action == "add":
        item.quantity_on_hand += data.quantity

    # Deduct available stock without consuming reserved units.
    elif data.action == "deduct":
        available_quantity = (
            item.quantity_on_hand - item.reserved_quantity
        )

        if data.quantity > available_quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Insufficient available stock for this deduction."
                ),
            )

        item.quantity_on_hand -= data.quantity

    # Set total stock to a specified amount.
    elif data.action == "set":
        if data.quantity < item.reserved_quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Stock cannot be set below the reserved quantity."
                ),
            )

        item.quantity_on_hand = data.quantity

    # Update the low-stock threshold when supplied.
    if data.low_stock_threshold is not None:
        item.low_stock_threshold = data.low_stock_threshold

    actual_change = item.quantity_on_hand - previous_quantity

    # Prevent an internal caller from choosing a misleading
    # responsible_user value for the transaction record.
    responsible_user = (
        "return-service"
        if current_user.get("service")
        else data.responsible_user
    )

    transaction = InventoryTransaction(
        product_id=product_id,
        quantity_change=actual_change,
        reason=data.reason,
        responsible_user=responsible_user,
    )

    db.add(transaction)
    db.commit()
    db.refresh(item)

    return item


# --------------------------------------------------
# Reserve stock for an order
# Only trusted internal services are allowed.
# --------------------------------------------------

@app.post(
    "/inventory/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def reserve_stock(
    data: ReservationCreate,
    principal: dict = Depends(get_user_or_internal_service),
    db: Session = Depends(get_db),
):
    # Only trusted internal services may create reservations.
    if not principal.get("service"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal service credentials are required.",
        )

    # Ensure that an inventory record exists.
    item_exists = (
        db.query(InventoryItem.id)
        .filter(InventoryItem.product_id == data.product_id)
        .first()
    )

    if item_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found for this product.",
        )

    # Atomically check stock availability and reserve quantity.
    updated_rows = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.product_id == data.product_id,
            (
                InventoryItem.quantity_on_hand
                - InventoryItem.reserved_quantity
            ) >= data.quantity,
        )
        .update(
            {
                InventoryItem.reserved_quantity:
                    InventoryItem.reserved_quantity + data.quantity
            },
            synchronize_session=False,
        )
    )

    if updated_rows == 0:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient available stock for this reservation.",
        )

    reservation = StockReservation(
        product_id=data.product_id,
        quantity=data.quantity,
        status="active",
        order_reference=data.order_reference,
    )

    db.add(reservation)
    db.flush()

    transaction = InventoryTransaction(
        product_id=data.product_id,
        quantity_change=0,
        reason=f"Reservation #{reservation.id} created",
        responsible_user=data.requested_by,
    )

    db.add(transaction)
    db.commit()
    db.refresh(reservation)

    return reservation


# --------------------------------------------------
# Release an active stock reservation
# Only trusted internal services are allowed.
# --------------------------------------------------

@app.post(
    "/inventory/reservations/{reservation_id}/release",
    response_model=ReservationResponse,
)
def release_reservation(
    reservation_id: int,
    principal: dict = Depends(get_user_or_internal_service),
    db: Session = Depends(get_db),
):
    # Only trusted internal services may release reservations.
    if not principal.get("service"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal service credentials are required.",
        )

    reservation = (
        db.query(StockReservation)
        .filter(StockReservation.id == reservation_id)
        .first()
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found.",
        )

    if reservation.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This reservation is no longer active.",
        )

    # Reduce reserved quantity without changing physical stock.
    updated_rows = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.product_id == reservation.product_id,
            InventoryItem.reserved_quantity >= reservation.quantity,
        )
        .update(
            {
                InventoryItem.reserved_quantity:
                    InventoryItem.reserved_quantity - reservation.quantity
            },
            synchronize_session=False,
        )
    )

    if updated_rows == 0:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The reservation could not be released safely.",
        )

    reservation.status = "released"

    transaction = InventoryTransaction(
        product_id=reservation.product_id,
        quantity_change=0,
        reason=f"Reservation #{reservation.id} released",
    )

    db.add(transaction)
    db.commit()
    db.refresh(reservation)

    return reservation


# --------------------------------------------------
# Get inventory transaction history for a product
# --------------------------------------------------

@app.get(
    "/inventory/{product_id}/transactions",
    response_model=list[InventoryTransactionResponse],
)
def get_inventory_transactions(
    product_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    item_exists = (
        db.query(InventoryItem.id)
        .filter(InventoryItem.product_id == product_id)
        .first()
    )

    if item_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found for this product.",
        )

    return (
        db.query(InventoryTransaction)
        .filter(InventoryTransaction.product_id == product_id)
        .order_by(InventoryTransaction.id.desc())
        .limit(limit)
        .all()
    )