
from datetime import date, datetime
from decimal import Decimal

import os
import httpx

from fastapi import FastAPI, HTTPException, Query

from .schemas import (
    InventoryItemReport,
    InventoryReport,
    OrdersReport,
    SalesReport,
    TopProduct,
    TopProductsReport,
)


# Addresses of the services that provide our business data
ORDER_SERVICE_URL = "http://127.0.0.1:8005"
INVENTORY_SERVICE_URL = "http://127.0.0.1:8003"


# Internal authentication for requests to the Order service
def get_internal_service_headers() -> dict:
    token = os.getenv("INTERNAL_SERVICE_TOKEN")

    if not token:
        raise HTTPException(
            status_code=500,
            detail="INTERNAL_SERVICE_TOKEN is not configured.",
        )

    return {
        "X-Internal-Service-Token": token
    }


# Create the FastAPI application
app = FastAPI(
    title="Analytics and Reporting Service",
    description="Sales, order, inventory, and popular product reports.",
    version="1.0.0",
)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Analytics and Reporting Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Fetch data from another microservice
def fetch_service_data(
    url: str,
    headers: dict | None = None,
):
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=10.0,
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to service: {url}",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=503,
            detail=f"Upstream service returned status {response.status_code}.",
        )

    return response.json()


# Retrieve orders from the Order Management Service
def fetch_orders():
    orders = fetch_service_data(
        f"{ORDER_SERVICE_URL}/orders",
        headers=get_internal_service_headers(),
    )

    if not isinstance(orders, list):
        raise HTTPException(
            status_code=502,
            detail="Order Service returned an unexpected response.",
        )

    return orders


# Retrieve inventory from the Inventory Service
def fetch_inventory():
    inventory = fetch_service_data(
        f"{INVENTORY_SERVICE_URL}/inventory"
    )

    if not isinstance(inventory, list):
        raise HTTPException(
            status_code=502,
            detail="Inventory Service returned an unexpected response.",
        )

    return inventory


# Filter orders using optional date parameters
def filter_orders(
    orders: list,
    start_date: date | None,
    end_date: date | None,
):
    filtered = []

    for order in orders:
        created_at = datetime.fromisoformat(
            order["created_at"].replace("Z", "+00:00")
        ).date()

        if start_date is not None and created_at < start_date:
            continue

        if end_date is not None and created_at > end_date:
            continue

        filtered.append(order)

    return filtered


# Validate report date ranges
def validate_dates(
    start_date: date | None,
    end_date: date | None,
):
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date.",
        )


# Sales report
@app.get("/analytics/sales", response_model=SalesReport)
def get_sales_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    validate_dates(start_date, end_date)

    orders = filter_orders(
        fetch_orders(),
        start_date,
        end_date,
    )

    cancelled_orders = sum(
        1 for order in orders
        if order["status"] == "Cancelled"
    )

    completed_orders = sum(
        1 for order in orders
        if order["status"] == "Delivered"
    )

    # Count orders that have passed the initial pending stage.
    # This is an operational sales estimate, not verified payment revenue.
    revenue_statuses = {
        "Confirmed",
        "Processing",
        "Shipped",
        "Delivered",
    }

    recognized_revenue = sum(
        (
            Decimal(str(order["total_amount"]))
            for order in orders
            if order["status"] in revenue_statuses
        ),
        Decimal("0.00"),
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_orders": len(orders),
        "cancelled_orders": cancelled_orders,
        "completed_orders": completed_orders,
        "recognized_revenue": recognized_revenue,
    }


# Order status report
@app.get("/analytics/orders", response_model=OrdersReport)
def get_orders_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    validate_dates(start_date, end_date)

    orders = filter_orders(
        fetch_orders(),
        start_date,
        end_date,
    )

    status_counts = {}

    for order in orders:
        order_status = order["status"]

        status_counts[order_status] = (
            status_counts.get(order_status, 0) + 1
        )

    cancelled_orders = status_counts.get("Cancelled", 0)

    cancellation_rate = (
        cancelled_orders / len(orders) * 100
        if orders
        else 0.0
    )

    return {
        "total_orders": len(orders),
        "status_counts": status_counts,
        "cancelled_orders": cancelled_orders,
        "cancellation_rate_percent": round(
            cancellation_rate,
            2,
        ),
    }


# Inventory report
@app.get(
    "/analytics/inventory",
    response_model=InventoryReport,
)
def get_inventory_report():
    inventory = fetch_inventory()

    items = []

    total_units = 0
    reserved_units = 0
    available_units = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for record in inventory:
        on_hand = record["quantity_on_hand"]
        reserved = record["reserved_quantity"]
        threshold = record["low_stock_threshold"]

        available = max(on_hand - reserved, 0)

        total_units += on_hand
        reserved_units += reserved
        available_units += available

        if available == 0:
            out_of_stock_count += 1
        elif available <= threshold:
            low_stock_count += 1

        items.append(
            InventoryItemReport(
                product_id=record["product_id"],
                quantity_on_hand=on_hand,
                reserved_quantity=reserved,
                available_quantity=available,
                low_stock_threshold=threshold,
            )
        )

    return {
        "total_products": len(items),
        "total_units": total_units,
        "reserved_units": reserved_units,
        "available_units": available_units,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "items": items,
    }


# Top-selling products report
@app.get(
    "/analytics/top-products",
    response_model=TopProductsReport,
)
def get_top_products(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
):
    validate_dates(start_date, end_date)

    orders = filter_orders(
        fetch_orders(),
        start_date,
        end_date,
    )

    totals = {}

    # Cancelled orders are excluded from these sales totals.
    for order in orders:
        if order["status"] == "Cancelled":
            continue

        for item in order.get("items", []):
            product_id = item["product_id"]

            if product_id not in totals:
                totals[product_id] = {
                    "product_id": product_id,
                    "product_name": item["product_name"],
                    "quantity_sold": 0,
                    "revenue": Decimal("0.00"),
                }

            totals[product_id]["quantity_sold"] += item["quantity"]

            totals[product_id]["revenue"] += Decimal(
                str(item["line_total"])
            )

    products = [
        TopProduct(**entry)
        for entry in totals.values()
    ]

    products.sort(
        key=lambda product: (
            product.quantity_sold,
            product.revenue,
        ),
        reverse=True,
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "items": products[:limit],
    }
