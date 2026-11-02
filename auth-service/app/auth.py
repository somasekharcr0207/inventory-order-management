import os
import jwt
import secrets
import hashlib

from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash

# Password hashing
password_hash = PasswordHash.recommended()

# JWT secret key
SECRET_KEY = os.getenv("AUTH_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "Set the AUTH_SECRET_KEY environment variable before starting the service."
    )

ALGORITHM = "HS256"

# Access token expires after 30 minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Refresh token expires after 7 days
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    user_id: int,
    username: str,
    role: str,
) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def get_refresh_token_expiry() -> int:
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    return int(expires_at.timestamp())


def get_current_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())