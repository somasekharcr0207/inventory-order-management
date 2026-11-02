import os
import secrets

import jwt

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


# --------------------------------------------------
# JWT Configuration
# --------------------------------------------------

SECRET_KEY = os.getenv("AUTH_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "AUTH_SECRET_KEY must be configured before starting the service."
    )

ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------
# Decode and validate JWT
# --------------------------------------------------

def decode_user_token(token: str) -> dict:
    """Validate JWT and return authenticated user information."""

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    user_id = payload.get("user_id")
    role = payload.get("role")

    if (
        not isinstance(username, str)
        or not username
        or not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
        or not isinstance(role, str)
        or not role
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing required information.",
        )

    return {
        "username": username,
        "user_id": user_id,
        "role": role,
        "service": False,
    }


# --------------------------------------------------
# Authenticate current user
# --------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:
    """Require a valid Customer or Administrator JWT."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decode_user_token(credentials.credentials)


# --------------------------------------------------
# Authenticate user or internal service
# --------------------------------------------------

def get_user_or_internal_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    internal_token: str | None = Header(
        default=None,
        alias="X-Internal-Service-Token",
    ),
) -> dict:
    """Authenticate either a user JWT or trusted internal service."""

    # Validate internal service token.
    if internal_token is not None:

        expected_token = os.getenv("INTERNAL_SERVICE_TOKEN")

        if (
            not expected_token
            or not secrets.compare_digest(
                internal_token,
                expected_token,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid internal service credentials.",
            )

        return {
            "username": None,
            "user_id": None,
            "role": "InternalService",
            "service": True,
        }

    # Otherwise require a valid user JWT.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decode_user_token(credentials.credentials)


# --------------------------------------------------
# Administrator Authentication
# --------------------------------------------------

def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allow only Administrators."""

    if current_user["role"] != "Administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission is required.",
        )

    return current_user


# --------------------------------------------------
# Administrator or Internal Service Authentication
# --------------------------------------------------

def require_admin_or_internal_service(
    principal: dict = Depends(get_user_or_internal_service),
) -> dict:
    """Allow Administrators or authenticated internal services."""

    if principal.get("service") is True:
        return principal

    if principal.get("role") != "Administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission is required.",
        )

    return principal