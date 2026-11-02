from .security import require_admin
from decimal import Decimal
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Product
from .schemas import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)


# Create the product database tables
Base.metadata.create_all(bind=engine)


# Create the FastAPI application
app = FastAPI(
    title="Product Catalog Service",
    description="Manage products in the Inventory and Order Management System.",
    version="1.0.0",
)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Product Catalog Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Create a product
@app.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = Product(**data.model_dump())

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


# Get all products, with search, filters, sorting, and pagination
@app.get("/products", response_model=ProductListResponse)
def list_products(
    q: str | None = Query(default=None, max_length=150),
    category: str | None = Query(default=None, max_length=100),
    min_price: Decimal | None = Query(default=None, gt=0),
    max_price: Decimal | None = Query(default=None, gt=0),
    sort_by: Literal["name", "price", "created_at"] = "name",
    sort_order: Literal["asc", "desc"] = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    # Search product names and descriptions
    if q:
        search_term = f"%{q}%"

        query = query.filter(
            Product.name.ilike(search_term)
            | Product.description.ilike(search_term)
        )

    # Filter products by category
    if category:
        query = query.filter(Product.category.ilike(category))

    # Filter by minimum price
    if min_price is not None:
        query = query.filter(Product.price >= min_price)

    # Filter by maximum price
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if min_price is not None and max_price is not None:
        if min_price > max_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_price cannot be greater than max_price.",
            )

    # Calculate how many products match the filters
    total = query.count()

    # Apply sorting
    sort_columns = {
        "name": Product.name,
        "price": Product.price,
        "created_at": Product.created_at,
    }

    sort_column = sort_columns[sort_by]

    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size

    products = (
        query.offset(offset)
        .limit(page_size)
        .all()
    )

    return {
        "items": products,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# Get one product by ID
@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    return product


# Update a product
@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Required database fields cannot be set to null
    for field in ("name", "category", "price"):
        if field in update_data and update_data[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null.",
            )

    # Apply the supplied updates
    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


# Delete a product
@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: int,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    db.delete(product)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)