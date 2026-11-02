import httpx

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import Review
from .schemas import (
    ReviewCreate,
    ReviewResponse,
    ReviewStatusUpdate,
    ReviewSummaryResponse,
    ReviewUpdate,
)


# Product Catalog Service address
PRODUCT_SERVICE_URL = "http://127.0.0.1:8002"


# Create database tables
Base.metadata.create_all(bind=engine)


# Create FastAPI application
app = FastAPI(
    title="Review and Rating Service",
    description="Manage product reviews and ratings.",
    version="1.0.0",
)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Review and Rating Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Check whether a product exists
def check_product_exists(product_id: int):
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
            detail="Product not found.",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve product information.",
        )


# Create a review
@app.post(
    "/reviews",
    response_model=ReviewResponse,
    status_code=201,
)
def create_review(
    data: ReviewCreate,
    db: Session = Depends(get_db),
):
    # Verify that the product exists.
    check_product_exists(data.product_id)

    # Prevent the same user from creating multiple reviews
    # for the same product.
    existing_review = (
        db.query(Review)
        .filter(
            Review.user_id == data.user_id,
            Review.product_id == data.product_id,
        )
        .first()
    )

    if existing_review:
        raise HTTPException(
            status_code=409,
            detail=(
                "You have already reviewed this product. "
                "Update your existing review instead."
            ),
        )

    review = Review(
        user_id=data.user_id,
        product_id=data.product_id,
        rating=data.rating,
        title=data.title,
        comment=data.comment,
        status="Pending",
    )

    db.add(review)

    try:
        db.commit()
        db.refresh(review)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="A review for this product already exists for this user.",
        )

    return review


# Get approved reviews for a product
@app.get(
    "/products/{product_id}/reviews",
    response_model=list[ReviewResponse],
)
def get_product_reviews(
    product_id: int,
    db: Session = Depends(get_db),
):
    check_product_exists(product_id)

    return (
        db.query(Review)
        .filter(
            Review.product_id == product_id,
            Review.status == "Approved",
        )
        .order_by(Review.id.desc())
        .all()
    )


# Get average rating and review count
@app.get(
    "/products/{product_id}/reviews/summary",
    response_model=ReviewSummaryResponse,
)
def get_review_summary(
    product_id: int,
    db: Session = Depends(get_db),
):
    check_product_exists(product_id)

    result = (
        db.query(
            func.avg(Review.rating),
            func.count(Review.id),
        )
        .filter(
            Review.product_id == product_id,
            Review.status == "Approved",
        )
        .first()
    )

    average_rating, review_count = result

    return {
        "product_id": product_id,
        "average_rating": (
            round(float(average_rating), 2)
            if average_rating is not None
            else None
        ),
        "review_count": review_count,
    }


# Update an existing review
@app.put(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
)
def update_review(
    review_id: int,
    data: ReviewUpdate,
    user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    review = (
        db.query(Review)
        .filter(
            Review.id == review_id,
            Review.user_id == user_id,
        )
        .first()
    )

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review not found for this user.",
        )

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null.",
            )

        setattr(review, field, value)

    # An edited review must be reviewed by a moderator again.
    review.status = "Pending"

    db.commit()
    db.refresh(review)

    return review


# Delete a review
@app.delete(
    "/reviews/{review_id}",
    status_code=204,
)
def delete_review(
    review_id: int,
    user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    review = (
        db.query(Review)
        .filter(
            Review.id == review_id,
            Review.user_id == user_id,
        )
        .first()
    )

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review not found for this user.",
        )

    db.delete(review)
    db.commit()

    return Response(status_code=204)


# Moderate a review
@app.patch(
    "/reviews/{review_id}/status",
    response_model=ReviewResponse,
)
def moderate_review(
    review_id: int,
    data: ReviewStatusUpdate,
    db: Session = Depends(get_db),
):
    review = (
        db.query(Review)
        .filter(Review.id == review_id)
        .first()
    )

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review not found.",
        )

    review.status = data.status

    db.commit()
    db.refresh(review)

    return review