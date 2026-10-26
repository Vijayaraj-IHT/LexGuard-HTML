from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import bcrypt
import jwt
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.services.crypto_service import verify_csrf_token

# Optional bearer scheme for swagger UI docs testing
bearer_scheme = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    """Hashes a password with salt using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    subject: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates a signed JWT access token containing user id and role claim."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "user_id": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_token(
    request: Request,
    bearer_auth: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """
    Extracts the JWT access token prioritizing the HttpOnly secure cookie
    with fallback to Authorization: Bearer header.
    """
    # 1. Check HttpOnly cookie first (secure standard)
    cookie_token = request.cookies.get(settings.COOKIE_NAME)
    if cookie_token:
        return cookie_token

    # 2. Check Bearer Authorization header
    if bearer_auth and bearer_auth.credentials:
        return bearer_auth.credentials

    # 3. Direct Authorization header parse
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Access token missing.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_payload(
    token: str = Depends(extract_token),
) -> Dict[str, Any]:
    """Dependency that decodes token and yields payload containing sub and role."""
    return decode_access_token(token)


def get_current_user(
    request: Request,
    payload: Dict[str, Any] = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """
    Dependency that resolves the active user from the database.
    Lazy imports models to avoid circular dependencies.
    """
    from app.models.user import User

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
        )

    if user.status != "active":
        if user.status == "suspended":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This user account has been suspended.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending verification or inactive. Active account required.",
        )

    return user


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Dependency that returns the active user if authenticated, or None for public requests.
    """
    from app.models.user import User

    token = None
    cookie_token = request.cookies.get(settings.COOKIE_NAME)
    if cookie_token:
        token = cookie_token
    else:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id, User.status == "active").first()
    except Exception:
        return None


def _canonical_role(role: str) -> str:
    """Map legacy staff spellings to the two staff privilege levels."""
    normalized = (role or "").strip().lower()
    if normalized == "senior_staff":
        return "senior_staff"
    if normalized in {"staff", "court_staff", "junior_staff"}:
        return "court_staff"
    return normalized


# Public alias for endpoint-level checks that cannot use ``require_role``.
canonical_role = _canonical_role


def require_role(allowed_roles: List[str]):
    """
    Role-Based Access Control (RBAC) dependency factory.

    ``staff``/``court_staff`` denote the ordinary court-staff level. Senior
    staff inherit ordinary staff access, but a senior-only requirement is
    strict: legacy ``staff``, ``court_staff`` and ``junior_staff`` accounts
    do not satisfy it.
    """
    allowed = {(role or "").strip().lower() for role in allowed_roles}
    expanded_allowed = set()
    for role in allowed:
        if role in {"staff", "court_staff", "junior_staff"}:
            expanded_allowed.update({"court_staff", "senior_staff"})
        else:
            expanded_allowed.add(role)

    def role_checker(
        current_user=Depends(get_current_user),
    ):
        user_role = _canonical_role(current_user.role)
        if user_role not in expanded_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: role '{current_user.role}' lacks permission for this resource.",
            )
        return current_user

    return role_checker


def verify_csrf_header(request: Request):
    """
    Validates CSRF header for state-changing HTTP requests when
    authenticated via cookie, preventing Cross-Site Request Forgery.
    """
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        # Only enforce if authenticating via cookie
        if settings.COOKIE_NAME in request.cookies:
            csrf_token = request.headers.get(settings.CSRF_HEADER_NAME)
            expected_csrf = request.cookies.get("lexguard_csrf_token")
            if not verify_csrf_token(csrf_token or "", expected_csrf or ""):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token validation failed.",
                )
    return True
