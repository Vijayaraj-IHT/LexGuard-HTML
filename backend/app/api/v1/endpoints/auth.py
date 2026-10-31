from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.token import TokenResponse
from app.services.crypto_service import generate_csrf_token
from app.services.audit_service import log_audit_event
from app.core.rate_limit import rate_limit

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))])
def register(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Registers a new user account with role-specific initial status.
    - Public users are active immediately.
    - Advocates and Scholars start as 'pending_verification' pending credential check.
    - Court staff accounts require pre-provisioning or senior staff approval.
    """
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    # Enforce that staff accounts cannot be registered publicly
    if user_in.role in ["court_staff", "senior_staff", "staff", "junior_staff"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Judicial staff accounts cannot be registered publicly.",
        )

    # Initial status based on role:
    # Public accounts are active immediately; advocates and scholars start pending verification
    if user_in.role == "public":
        initial_status = "active"
    else:
        initial_status = "pending_verification"

    user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role,
        status=initial_status,
        credential_id=user_in.credential_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Record registration in immutable audit trail
    log_audit_event(
        db=db,
        action="REGISTER",
        user_id=user.id,
        details=f"User registered with role: {user.role}, initial status: {user.status}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return user


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit(max_requests=15, window_seconds=60))])
def login(
    credentials: UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticates user, sets HttpOnly secure cookie and CSRF token,
    and returns token metadata.
    Enforces active-account status for login.
    """
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    # Enforce active account status
    if user.status != "active":
        if user.status == "suspended":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended. Please contact the court administrator.",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending verification or inactive. Privileged access not permitted.",
        )

    access_token = create_access_token(
        subject=user.id,
        role=user.role,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"name": user.name, "email": user.email, "status": user.status},
    )

    csrf_token = generate_csrf_token()

    # Set HttpOnly Cookie (OWASP Top 10 A07 Defense - No localStorage)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )

    # Set CSRF Token in client-readable cookie for double-submit cookie pattern
    response.set_cookie(
        key="lexguard_csrf_token",
        value=csrf_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )

    # Record login audit event
    log_audit_event(
        db=db,
        action="LOGIN",
        user_id=user.id,
        details=f"Successful login for role: {user.role}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        user_id=user.id,
        name=user.name,
        csrf_token=csrf_token,
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logs out user by removing authentication cookies and recording the event."""
    response.delete_cookie(settings.COOKIE_NAME, path="/")
    response.delete_cookie("lexguard_csrf_token", path="/")

    log_audit_event(
        db=db,
        action="LOGOUT",
        user_id=current_user.id,
        details="User logged out",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {"status": "success", "message": "Successfully logged out."}


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Returns profile details of the currently authenticated user."""
    return current_user
