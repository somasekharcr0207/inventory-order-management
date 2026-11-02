# Inventory Order Management System

A Python-based microservices project for managing products, inventory,
orders, payments, notifications, reviews, coupons, returns, and
analytics.

## Project overview

The application is divided into independent FastAPI services. Each
service runs on its own port and exposes API endpoints documented
through Swagger UI.

## Technology stack

-   Python
-   FastAPI
-   Uvicorn
-   SQLite (local development databases)
-   JWT-based authentication
-   HTTP-based communication between services
-   Swagger UI / OpenAPI
-   PowerShell for local development

## Services and ports

  Service                  Port Swagger documentation
  ---------------------- ------ ----------------------------
  API Gateway              8000 http://127.0.0.1:8000/docs
  Auth Service             8001 http://127.0.0.1:8001/docs
  Product Service          8002 http://127.0.0.1:8002/docs
  Inventory Service        8003 http://127.0.0.1:8003/docs
  Order Service            8005 http://127.0.0.1:8005/docs
  Payment Service          8006 http://127.0.0.1:8006/docs
  Notification Service     8007 http://127.0.0.1:8007/docs
  Review Service           8008 http://127.0.0.1:8008/docs
  Coupon Service           8009 http://127.0.0.1:8009/docs
  Return Service           8010 http://127.0.0.1:8010/docs
  Analytics Service        8011 http://127.0.0.1:8011/docs

The Cart Service folder is present in the project, but its runtime setup
and endpoints have not yet been verified.

## Project structure

``` text
inventory-order-management/
├── api-gateway/
├── auth-service/
├── product-service/
├── inventory-service/
├── order-service/
├── payment-service/
├── notification-service/
├── review-service/
├── coupon-service/
├── return-service/
├── analytics-service/
├── cart-service/
├── postman/
├── requirements.txt
├── README.md
└── .gitignore
```

Each service contains its own application code. Local SQLite database
files may be created when services run.

## Prerequisites

-   Windows
-   Python 3.12 (or a compatible Python version used by the project)
-   PowerShell
-   Visual Studio Code (recommended)

## Setup

Open PowerShell and move to the project folder:

``` powershell
cd D:\inventory-order-management
```

Create a virtual environment if one does not already exist:

``` powershell
python -m venv venv
```

Activate it:

``` powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

``` powershell
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, run this command in
the current PowerShell window and then activate again:

``` powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## Environment variables

Services that use the shared development secrets must receive the same
values in their respective PowerShell terminals. For local testing only,
set:

``` powershell
$env:AUTH_SECRET_KEY = "local-dev-only-change-this-before-deployment-123456789"
$env:INTERNAL_SERVICE_TOKEN = "local-internal-service-token-change-before-deployment-987654321"
```

These are development placeholders. Replace them with strong private
values before deployment. Do not commit real secrets, access tokens, or
`.env` files to GitHub.

## Starting a service

Keep each service running in its own PowerShell terminal. Example for
the API Gateway:

``` powershell
cd D:\inventory-order-management\api-gateway
$env:AUTH_SECRET_KEY = "local-dev-only-change-this-before-deployment-123456789"
$env:INTERNAL_SERVICE_TOKEN = "local-internal-service-token-change-before-deployment-987654321"
& "D:\inventory-order-management\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
```

Example for the Product Service:

``` powershell
cd D:\inventory-order-management\product-service
$env:AUTH_SECRET_KEY = "local-dev-only-change-this-before-deployment-123456789"
$env:INTERNAL_SERVICE_TOKEN = "local-internal-service-token-change-before-deployment-987654321"
& "D:\inventory-order-management\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8002
```

For another service, use its folder and port from the table above. The
service must be started using its actual `app.main:app` entry point.
Keep the terminal open while using that service.

## Checking service health

Open the health endpoint for each service in a browser or PowerShell.
Example:

``` powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

A healthy response indicates that the service process is responding. A
service may need to be restarted if its terminal was closed.

## API testing

Swagger UI is available at `/docs` for each service. The project has
also been tested through PowerShell HTTP requests and the `postman/`
project folder.

Some endpoints require a valid access token. A `401 Unauthorized`
response when calling a protected endpoint without a token is expected.

## Implemented areas

The project has been exercised with tests covering:

-   User authentication and token-based access
-   Product creation and retrieval
-   Inventory quantity updates and reservations
-   Order creation, status changes, and cancellation
-   Payment status handling and idempotency checks
-   Notifications and review status updates
-   Coupon redemption
-   Return processing and inventory restocking
-   Analytics reports for sales, orders, inventory, and top products
-   Internal service-to-service authentication

## Important development notes

-   Payment processing in the current project is simulated; this README
    does not claim that real money is charged.
-   Refund status handling is simulated; it does not claim that money is
    transferred to a customer.
-   SQLite database files contain local development data and should not
    normally be committed.
-   The Cart Service folder exists, but it is not included in the
    verified service/port list above.
-   Verify all environment variables and service URLs before running the
    project on another computer.

## Author

Add your name and contact details here before submitting the project.
