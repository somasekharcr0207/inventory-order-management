from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .models import CartItem, WishlistItem
from .schemas import (
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartResponse,
    WishlistItemCreate,
    WishlistItemResponse,
)
from .security import get_current_user


# Create database tables.
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Shopping Cart and Wishlist Service",
    description="Manage each authenticated user's cart and wishlist.",
    version="1.1.0",
)


@app.get("/")
def home():
    return {
        "message": "Shopping Cart Service is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


# Get only the authenticated user's cart.
@app.get("/cart", response_model=CartResponse)
def get_cart(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    items = (
        db.query(CartItem)
        .filter(CartItem.user_id == user_id)
        .order_by(CartItem.id.asc())
        .all()
    )

    total_items = sum(item.quantity for item in items)

    return {
        "items": items,
        "total_items": total_items,
    }


# Add a product to the authenticated user's cart.
@app.post(
    "/cart/items",
    response_model=CartItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_cart_item(
    data: CartItemCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    existing_item = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == user_id,
            CartItem.product_id == data.product_id,
        )
        .first()
    )

    if existing_item:
        existing_item.quantity += data.quantity
        db.commit()
        db.refresh(existing_item)
        return existing_item

    item = CartItem(
        user_id=user_id,
        product_id=data.product_id,
        quantity=data.quantity,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


# Update only the authenticated user's cart item.
@app.patch(
    "/cart/items/{item_id}",
    response_model=CartItemResponse,
)
def update_cart_item(
    item_id: int,
    data: CartItemUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    item = (
        db.query(CartItem)
        .filter(
            CartItem.id == item_id,
            CartItem.user_id == user_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found.",
        )

    item.quantity = data.quantity

    db.commit()
    db.refresh(item)

    return item


# Remove only the authenticated user's cart item.
@app.delete(
    "/cart/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_cart_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    item = (
        db.query(CartItem)
        .filter(
            CartItem.id == item_id,
            CartItem.user_id == user_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found.",
        )

    db.delete(item)
    db.commit()

    return None


# Get only the authenticated user's wishlist.
@app.get(
    "/wishlist",
    response_model=list[WishlistItemResponse],
)
def get_wishlist(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    return (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user_id)
        .order_by(WishlistItem.id.asc())
        .all()
    )


# Add a product to the authenticated user's wishlist.
@app.post(
    "/wishlist/items",
    response_model=WishlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_wishlist_item(
    data: WishlistItemCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    existing_item = (
        db.query(WishlistItem)
        .filter(
            WishlistItem.user_id == user_id,
            WishlistItem.product_id == data.product_id,
        )
        .first()
    )

    if existing_item:
        return existing_item

    item = WishlistItem(
        user_id=user_id,
        product_id=data.product_id,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


# Remove only the authenticated user's wishlist item.
@app.delete(
    "/wishlist/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_wishlist_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    item = (
        db.query(WishlistItem)
        .filter(
            WishlistItem.id == item_id,
            WishlistItem.user_id == user_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist item not found.",
        )

    db.delete(item)
    db.commit()

    return None