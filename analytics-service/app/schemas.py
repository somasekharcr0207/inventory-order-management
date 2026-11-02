from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SalesReport(BaseModel):
    start_date: date | None
    end_date: date | None
    total_orders: int
    cancelled_orders: int
    completed_orders: int
    recognized_revenue: Decimal


class OrdersReport(BaseModel):
    total_orders: int
    status_counts: dict[str, int]
    cancelled_orders: int
    cancellation_rate_percent: float


class InventoryItemReport(BaseModel):
    product_id: int
    quantity_on_hand: int
    reserved_quantity: int
    available_quantity: int
    low_stock_threshold: int


class InventoryReport(BaseModel):
    total_products: int
    total_units: int
    reserved_units: int
    available_units: int
    low_stock_count: int
    out_of_stock_count: int
    items: list[InventoryItemReport]


class TopProduct(BaseModel):
    product_id: int
    product_name: str
    quantity_sold: int
    revenue: Decimal


class TopProductsReport(BaseModel):
    start_date: date | None
    end_date: date | None
    items: list[TopProduct]