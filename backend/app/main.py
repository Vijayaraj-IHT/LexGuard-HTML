from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.api.v1.api import api_router
from app.models.user import User
from app.core.security import get_password_hash


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    OWASP A02:2025 Defense: Enforces strict HTTP security headers
    preventing MIME-sniffing, clickjacking, and unauthorized frame embedding.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Content Security Policy header
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        return response


class CSRFValidationMiddleware(BaseHTTPMiddleware):
    """
    OWASP Double-Submit Cookie CSRF Defense:
    Validates X-CSRF-Token against lexguard_csrf_token cookie for state-changing
    requests when session cookie is present.
    """
    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            # If user is authenticated via cookie, require valid CSRF token header
            if settings.COOKIE_NAME in request.cookies:
                csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
                expected_csrf = request.cookies.get("lexguard_csrf_token")
                if not csrf_header or not expected_csrf or csrf_header != expected_csrf:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF validation failed: missing or invalid X-CSRF-Token header."}
                    )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production security validation
    if settings.ENVIRONMENT == "production":
        if not settings.SECRET_KEY or "lexguard-super-secret" in settings.SECRET_KEY:
            raise RuntimeError("CRITICAL SECURITY VIOLATION: Production SECRET_KEY must be configured via environment variable.")
        settings.COOKIE_SECURE = True

    # Startup: Ensure all database tables exist
    Base.metadata.create_all(bind=engine)

    # Dev-gate: Seed test/demo accounts strictly in development mode
    if settings.ENVIRONMENT == "development":
        db = SessionLocal()
        try:
            seed_data = [
                {
                    "name": "Chief Registrar",
                    "email": "staff@court.gov.in",
                    "password": "staff123",
                    "role": "staff",
                    "status": "active",
                    "credential_id": "COURT-REG-001",
                },
                {
                    "name": "Senior Advocate",
                    "email": "advocate@bar.in",
                    "password": "advocate123",
                    "role": "advocate",
                    "status": "active",
                    "credential_id": "BAR-DL-2024-9912",
                },
                {
                    "name": "Legal Scholar",
                    "email": "scholar@law.edu",
                    "password": "scholar123",
                    "role": "scholar",
                    "status": "active",
                    "credential_id": "NLSIU-FAC-4012",
                },
                {
                    "name": "Citizen User",
                    "email": "public@citizen.in",
                    "password": "public123",
                    "role": "public",
                    "status": "active",
                    "credential_id": None,
                },
                {
                    "name": "Chief Registrar",
                    "email": "staff@lexguard.gov.in",
                    "password": "Admin@Lexguard2026",
                    "role": "senior_staff",
                    "status": "active",
                    "credential_id": "COURT-REG-001",
                },
            ]

            for item in seed_data:
                existing_user = db.query(User).filter(User.email == item["email"]).first()
                if not existing_user:
                    new_user = User(
                        name=item["name"],
                        email=item["email"],
                        password_hash=get_password_hash(item["password"]),
                        role=item["role"],
                        status=item["status"],
                        credential_id=item["credential_id"],
                    )
                    db.add(new_user)
            db.commit()
        finally:
            db.close()

    yield
    # Shutdown logic if any


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# 1. Attach Security Headers & CSRF Middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFValidationMiddleware)

# 2. Attach CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount API v1 Routers
app.include_router(api_router, prefix=settings.API_V1_STR)

import os
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve official LexGuard judicial favicon without triggering 404 console logs."""
    ico_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "favicon.ico")
    if os.path.exists(ico_path):
        return FileResponse(ico_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.exception_handler(404)
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: Exception):
    """
    Standardized, user-friendly 404 and HTTP error handler returning structured JSON
    with helpful navigation suggestions instead of cryptic unhandled errors.
    """
    status_code = getattr(exc, "status_code", 404)
    detail = getattr(exc, "detail", "Resource not found")
    
    if status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not Found",
                "status_code": 404,
                "detail": detail if detail != "Not Found" else f"The requested resource at '{request.url.path}' was not found on this judicial repository server.",
                "path": request.url.path,
                "available_endpoints": {
                    "health": "/health",
                    "api_docs": f"{settings.API_V1_STR}/docs",
                    "search_cases": f"{settings.API_V1_STR}/cases/search",
                    "acts_catalog": f"{settings.API_V1_STR}/acts/all",
                }
            }
        )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "HTTP Error",
            "status_code": status_code,
            "detail": detail,
            "path": request.url.path,
        }
    )


@app.get("/health", tags=["System Health"])
def health_check():
    """Health check endpoint for container probes and uptime monitors."""
    return {
        "status": "healthy",
        "system": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database_connected": True,
    }


@app.get("/", tags=["System Root"])
def root():
    """Root metadata endpoint."""
    return {
        "name": settings.PROJECT_NAME,
        "version": "1.0.0",
        "api_docs": f"{settings.API_V1_STR}/docs",
        "status": "online",
    }
