from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.api.v1.api import api_router
from app.models.user import User
from app.core.security import get_password_hash
from app.services.crypto_service import verify_csrf_token


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _resolve_frontend_dir() -> Path:
    configured = Path(settings.FRONTEND_DIR).expanduser()
    if not configured.is_absolute():
        configured = BACKEND_DIR / configured
    return configured.resolve()


FRONTEND_DIR = _resolve_frontend_dir()
FRONTEND_ENABLED = bool(settings.SERVE_FRONTEND and FRONTEND_DIR.is_dir())


def _resolve_storage_dir() -> Path:
    configured = Path(settings.STORAGE_DIR).expanduser()
    if not configured.is_absolute():
        configured = BACKEND_DIR / configured
    return configured.resolve()


def _is_api_path(path: str) -> bool:
    return path == settings.API_V1_STR or path.startswith(f"{settings.API_V1_STR}/")


def _content_security_policy(path: str) -> str:
    if _is_api_path(path):
        # Swagger/ReDoc load their bundles from jsDelivr when docs are enabled.
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none';"
        )

    # The zero-build frontend intentionally uses a small set of public CDNs
    # (Bootstrap, jQuery, Chart.js, PDF.js and Google Fonts) plus inline
    # page bootstrap scripts. Keep the allow-list explicit instead of using
    # a wildcard.
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
        "https://cdn.jsdelivr.net https://code.jquery.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
        "https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data: https://fonts.gstatic.com "
        "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
        "worker-src 'self' blob: https://cdnjs.cloudflare.com; "
        "child-src 'self' blob:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none';"
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    OWASP A02:2025 Defense: Enforces strict HTTP security headers
    preventing MIME-sniffing, clickjacking, and unauthorized frame embedding.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = _content_security_policy(request.url.path)

        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        is_https = request.url.scheme == "https" or forwarded_proto.split(",")[0].strip() == "https"
        if settings.ENVIRONMENT == "production" and is_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
                if not verify_csrf_token(csrf_header or "", expected_csrf or ""):
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

    # Startup: Ensure all database tables exist. Existing restored databases
    # still require the explicit Phase-0 migration for added columns/indexes;
    # deployment start scripts run that migration before Uvicorn when enabled.
    Base.metadata.create_all(bind=engine)
    _resolve_storage_dir().mkdir(parents=True, exist_ok=True)

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
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.ENABLE_API_DOCS else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.ENABLE_API_DOCS else None,
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
    """Serve the LexGuard favicon without triggering 404 console logs."""
    candidates = [
        FRONTEND_DIR / "favicon.ico",
        BACKEND_DIR / "storage" / "favicon.ico",
    ]
    for ico_path in candidates:
        if ico_path.is_file():
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

    # Browser navigations in single-service mode get the designed judicial
    # 404 page; API clients continue to receive structured JSON.
    accept = request.headers.get("accept", "")
    if (
        status_code == 404
        and FRONTEND_ENABLED
        and not _is_api_path(request.url.path)
        and "text/html" in accept
    ):
        frontend_404 = FRONTEND_DIR / "404.html"
        if frontend_404.is_file():
            return FileResponse(frontend_404, status_code=404, media_type="text/html")

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
                    "readiness": "/ready",
                    "api_docs": f"{settings.API_V1_STR}/docs" if settings.ENABLE_API_DOCS else None,
                    "frontend": "/" if FRONTEND_ENABLED else None,
                    "search_cases": f"{settings.API_V1_STR}/search/",
                    "acts_catalog": f"{settings.API_V1_STR}/statutes/acts",
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
    """Liveness probe: confirms only that the process can answer HTTP."""
    return {
        "status": "healthy",
        "system": settings.PROJECT_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "frontend_served": FRONTEND_ENABLED,
    }


def _readiness_checks() -> dict:
    """Return dependency/schema checks without exposing connection secrets."""
    checks = {
        "database": False,
        "schema": False,
        "storage": False,
        "frontend": (not settings.SERVE_FRONTEND) or FRONTEND_ENABLED,
    }
    details = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        required_columns = {
            "users": {"id", "email", "password_hash", "role", "status"},
            "cases": {"id", "file_hash", "judicial_seal", "status"},
            "audit_logs": {"id", "seq", "segment", "current_hash"},
        }
        missing = {}
        for table, columns in required_columns.items():
            if table not in tables:
                missing[table] = sorted(columns)
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            if not columns.issubset(present):
                missing[table] = sorted(columns - present)
        checks["schema"] = not missing
        if missing:
            details["missing_schema"] = missing
    except Exception as exc:  # readiness must report, not crash the probe
        details["database_error"] = exc.__class__.__name__

    storage_dir = _resolve_storage_dir()
    checks["storage"] = storage_dir.is_dir() and os.access(storage_dir, os.W_OK)
    details["storage_dir"] = str(storage_dir)

    return {
        "ready": all(checks.values()),
        "checks": checks,
        "details": details,
    }


@app.get("/ready", tags=["System Health"])
def readiness_check():
    """Readiness probe for DB/schema/storage/frontend dependencies."""
    result = _readiness_checks()
    return JSONResponse(
        status_code=200 if result["ready"] else 503,
        content={
            "status": "ready" if result["ready"] else "not_ready",
            "system": settings.PROJECT_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            **result,
        },
    )


def root_metadata():
    """Root metadata used when the frontend is hosted separately."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.APP_VERSION,
        "api_docs": f"{settings.API_V1_STR}/docs" if settings.ENABLE_API_DOCS else None,
        "health": "/health",
        "readiness": "/ready",
        "status": "online",
    }


class FrontendStaticFiles(StaticFiles):
    """Static frontend app that must not swallow API 404 semantics."""

    async def get_response(self, path: str, scope):
        full_path = scope.get("path", path)
        if _is_api_path(full_path):
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Not Found",
                    "status_code": 404,
                    "detail": f"The requested resource at '{full_path}' was not found on this judicial repository server.",
                    "path": full_path,
                    "available_endpoints": {
                        "health": "/health",
                        "readiness": "/ready",
                        "api_docs": f"{settings.API_V1_STR}/docs" if settings.ENABLE_API_DOCS else None,
                        "frontend": "/",
                    },
                },
            )

        response = await super().get_response(path, scope)
        accept = ""
        for header, value in scope.get("headers", []):
            if header == b"accept":
                accept = value.decode("latin-1")
                break
        if response.status_code == 404 and "text/html" in accept:
            frontend_404 = FRONTEND_DIR / "404.html"
            if frontend_404.is_file():
                return FileResponse(frontend_404, status_code=404, media_type="text/html")
        return response


app.add_api_route("/api", root_metadata, methods=["GET"], tags=["System Root"])
if not FRONTEND_ENABLED:
    app.add_api_route("/", root_metadata, methods=["GET"], tags=["System Root"])
else:
    # Mount last so API, health and readiness routes retain precedence.
    app.mount("/", FrontendStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
