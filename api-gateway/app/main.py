import uuid

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response


# Addresses of all backend microservices
SERVICES = {
    "auth": "http://127.0.0.1:8001",
    "products": "http://127.0.0.1:8002",
    "inventory": "http://127.0.0.1:8003",
    "cart": "http://127.0.0.1:8004",
    "wishlist": "http://127.0.0.1:8004",
    "orders": "http://127.0.0.1:8005",
    "payments": "http://127.0.0.1:8006",
    "notifications": "http://127.0.0.1:8007",
    "reviews": "http://127.0.0.1:8008",
    "coupons": "http://127.0.0.1:8009",
    "returns": "http://127.0.0.1:8010",
    "analytics": "http://127.0.0.1:8011",
}


# Create the API Gateway
app = FastAPI(
    title="Inventory and Order Management API Gateway",
    description="Central entry point for all backend microservices.",
    version="1.0.0",
)


# Allow requests from the local React development frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "Inventory and Order Management API Gateway",
        "status": "running",
        "services": {
            "auth": "http://127.0.0.1:8001",
            "products": "http://127.0.0.1:8002",
            "inventory": "http://127.0.0.1:8003",
            "cart": "http://127.0.0.1:8004",
            "orders": "http://127.0.0.1:8005",
            "payments": "http://127.0.0.1:8006",
            "notifications": "http://127.0.0.1:8007",
            "reviews": "http://127.0.0.1:8008",
            "coupons": "http://127.0.0.1:8009",
            "returns": "http://127.0.0.1:8010",
            "analytics": "http://127.0.0.1:8011",
        },
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


def find_service(path: str):
    """
    Identify which microservice should receive the request.
    """

    parts = path.strip("/").split("/")

    if not parts or not parts[0]:
        return None

    # Product review endpoints use /products/{id}/reviews.
    # Forward these to the Review Service instead of Product Catalog.
    if (
        len(parts) >= 3
        and parts[0] == "products"
        and parts[1].isdigit()
        and parts[2] == "reviews"
    ):
        return "reviews"

    # Otherwise, use the first URL segment to choose the service.
    service_name = parts[0]

    if service_name in SERVICES:
        return service_name

    return None


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_request(request: Request, path: str):
    """
    Forward requests to the appropriate microservice.
    """

    service_name = find_service(path)

    if service_name is None:
        raise HTTPException(
            status_code=404,
            detail="No microservice is configured for this path.",
        )

    service_url = SERVICES[service_name]

    target_url = f"{service_url}/{path}"

    # Preserve query parameters.
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Create or reuse a request correlation ID.
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Forward useful request headers.
    excluded_headers = {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
    }

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    }

    headers["X-Request-ID"] = request_id

    # Read the incoming request body.
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream_response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"The {service_name} service timed out.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=f"The {service_name} service is unavailable.",
        )

    # Exclude hop-by-hop headers and headers describing the upstream
    # encoded response body, because httpx may already decode it.
    response_excluded_headers = {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "content-length",
        "content-encoding",
    }

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in response_excluded_headers
    }

    response_headers["X-Request-ID"] = request_id

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )