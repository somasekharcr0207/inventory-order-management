import jwt

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_current_timestamp,
    get_refresh_token_expiry,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from .database import Base, engine, get_db
from .models import RefreshToken, User
from .schemas import UserLogin, UserRegister, UserResponse, RefreshRequest


# Create database tables
Base.metadata.create_all(bind=engine)


# Create FastAPI application
app = FastAPI(
    title="Inventory and Order Management - Authentication Service",
    description="Registration, login, refresh tokens, and JWT authentication",
    version="1.0.0",
)

bearer_scheme = HTTPBearer(auto_error=False)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Authentication Service is running",
        "docs": "/docs",
    }


# Health check
@app.get("/health")
def health():
    return {"status": "healthy"}


# Register a new customer
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    data: UserRegister,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter(
            (User.username == data.username)
            | (User.email == str(data.email))
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        )

    user = User(
        username=data.username,
        email=str(data.email),
        hashed_password=hash_password(data.password),
        role="Customer",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# Login and generate access and refresh tokens
@app.post("/auth/login")
def login_user(
    data: UserLogin,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.username == data.username)
        .first()
    )

    if user is None or not verify_password(
        data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate an access token
    access_token = create_access_token(
    user_id=user.id,
    username=user.username,
    role=user.role,
)

    # Generate a refresh token
    refresh_token = create_refresh_token()

    # Store only the refresh token's hash
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=get_refresh_token_expiry(),
    )

    db.add(token_record)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 1800,
    }


# Refresh access and refresh tokens
@app.post("/auth/refresh")
def refresh_access_token(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    # Hash the supplied refresh token
    supplied_hash = hash_refresh_token(data.refresh_token)

    # Find the matching token record
    token_record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == supplied_hash)
        .first()
    )

    current_time = get_current_timestamp()

    # Reject missing, revoked, or expired refresh tokens
    if (
        token_record is None
        or token_record.revoked_at is not None
        or token_record.expires_at <= current_time
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked refresh token.",
        )

    # Find the user who owns the token
    user = db.query(User).filter(
        User.id == token_record.user_id
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    # Revoke the old refresh token
    token_record.revoked_at = current_time

    # Generate new tokens
    new_access_token = create_access_token(
    user_id=user.id,
    username=user.username,
    role=user.role,
)

    new_refresh_token = create_refresh_token()

    # Store the hash of the new refresh token
    new_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_token),
        expires_at=get_refresh_token_expiry(),
    )

    db.add(new_record)
    db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 1800,
    }


# Validate the access token and identify the current user
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a username.",
        )

    user = db.query(User).filter(
        User.username == username
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    return user


# Get the currently authenticated user's details
@app.get("/auth/me", response_model=UserResponse)
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user