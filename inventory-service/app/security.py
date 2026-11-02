import os
import secrets

import jwt

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


# JWT configuration
SECRET_KEY = os.getenv("AUTH_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "AUTH_SECRET_KEY must be configured before starting the service."
    )

ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:
    """Validate a user's JWT access token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
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
    role = payload.get("role")

    if not username or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing required information.",
        )

    return {
        "username": username,
        "user_id": payload.get("user_id"),
        "role": role,
        "service": False,
    }


def get_user_or_internal_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    internal_token: str | None = Header(
        default=None,
        alias="X-Internal-Service-Token",
    ),
) -> dict:
    """Authenticate either a user or a trusted internal service."""

    # Authenticate internal service requests.
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
            "username": "return-service",
            "user_id": None,
            "role": "InternalService",
            "service": True,
        }

    # Otherwise, require a valid user JWT.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_current_user(credentials)


def require_inventory_manager(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allow only Administrators and Inventory Managers."""

    allowed_roles = {
        "Administrator",
        "Inventory Manager",
    }

    if current_user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Administrator or Inventory Manager permission "
                "is required."
            ),
        )

    return current_user