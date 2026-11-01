"""System / database preflight endpoints.

Read-only summaries are public; starting a run is restricted to court staff and is
throttled. Runs execute in a background task with a dedicated session, because they
can take seconds on a large corpus and must not hold the request's connection.

Advisory locking happens inside the service: on PostgreSQL a second concurrent run
returns ``BUSY`` instead of racing, and on SQLite the run is refused with
``POSTGRES_REQUIRED`` unless ``PREFLIGHT_ALLOW_NON_POSTGRES`` is enabled.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.security import require_role
from app.models.preflight import (
    PREFLIGHT_ACTIVE_STATUSES,
    PREFLIGHT_STATUS_QUEUED,
    CasePreflightRun,
)
from app.models.user import User
from app.services.case_preflight_service import (
    ensure_preflight_schema,
    latest_run,
    run_case_preflight,
    run_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- schemas
class PreflightRunSummary(BaseModel):
    """Path-free view of a preflight run."""

    id: str
    status: str
    mode: str
    trigger: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total_cases: int = 0
    verified_count: int = 0
    missing_count: int = 0
    mismatch_count: int = 0
    duplicate_hash_count: int = 0
    invalid_metadata_count: int = 0
    report: Dict[str, Any] = Field(default_factory=dict)


class PreflightQueuedResponse(BaseModel):
    id: str
    status: str
    mode: str
    message: str


# --------------------------------------------------------------------------- helpers
def _ensure_schema_if_missing(db: Session) -> None:
    """Create the ledger table (and cases indexes) if this database predates it.

    ``app.main``'s lifespan already runs ``Base.metadata.create_all``, but a process
    that serves the app without lifespan (tests, some WSGI shims) would otherwise
    raise on the first read, so reads self-heal once.
    """
    bind = db.get_bind()
    if not inspect(bind).has_table(CasePreflightRun.__tablename__):
        ensure_preflight_schema(bind)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _throttled(detail: Dict[str, Any], retry_after: int) -> JSONResponse:
    """429 that keeps its ``Retry-After`` header.

    Returned rather than raised: the app-wide StarletteHTTPException handler
    (``app/main.py``) rebuilds error bodies and drops exception headers, so raising
    would silently lose ``Retry-After``.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": detail},
        headers={"Retry-After": str(retry_after)},
    )


def _throttle(db: Session) -> Optional[JSONResponse]:
    """Return a 429 response while a run is active or the previous one is too recent."""
    active = (
        db.query(CasePreflightRun)
        .filter(CasePreflightRun.status.in_(PREFLIGHT_ACTIVE_STATUSES))
        .order_by(CasePreflightRun.started_at.desc())
        .first()
    )
    if active is not None:
        return _throttled(
            {"message": "A preflight run is already in progress.", "run_id": active.id},
            settings.PREFLIGHT_THROTTLE_SECONDS,
        )

    last = latest_run(db)
    if last is not None and last.finished_at is not None:
        finished = _as_utc(last.finished_at)
        elapsed = (datetime.now(timezone.utc) - finished).total_seconds() if finished else None
        if elapsed is not None and elapsed < settings.PREFLIGHT_THROTTLE_SECONDS:
            retry_after = max(1, int(settings.PREFLIGHT_THROTTLE_SECONDS - elapsed))
            return _throttled(
                {
                    "message": "Preflight ran recently; wait before running it again.",
                    "retry_after_seconds": retry_after,
                    "run_id": last.id,
                },
                retry_after,
            )
    return None


def _execute_preflight(run_id: str, mode: str) -> None:
    """Background worker: runs with its own session so the request can return."""
    db = SessionLocal()
    try:
        run = db.query(CasePreflightRun).filter(CasePreflightRun.id == run_id).one_or_none()
        if run is None:  # pragma: no cover - would mean the row vanished
            logger.error("preflight run %s disappeared before execution", run_id)
            return
        run_case_preflight(
            db,
            mode=mode,
            trigger=run.trigger,
            batch_size=settings.PREFLIGHT_DEFAULT_BATCH_SIZE,
            allow_non_postgres=settings.PREFLIGHT_ALLOW_NON_POSTGRES,
            run=run,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("background preflight run %s failed", run_id)
    finally:
        db.close()


# --------------------------------------------------------------------------- routes
@router.get(
    "/case-preflight/latest",
    response_model=PreflightRunSummary,
    summary="Latest case-file preflight result (public)",
)
def get_latest_case_preflight(db: Session = Depends(get_db)):
    """Most recent preflight run. Contains no local filesystem paths."""
    _ensure_schema_if_missing(db)
    run = latest_run(db)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No case preflight has been recorded yet.",
        )
    return PreflightRunSummary(**run_summary(run, max_samples=settings.PREFLIGHT_MAX_SAMPLES))


@router.post(
    "/case-preflight/run",
    response_model=PreflightQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a case-file preflight run (court staff, throttled)",
)
def start_case_preflight(
    background_tasks: BackgroundTasks,
    mode: str = Query(default="verify", pattern="^(verify|repair)$"),
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """Queue a run. Advisory locking and throttling prevent concurrent sweeps."""
    _ensure_schema_if_missing(db)
    throttled = _throttle(db)
    if throttled is not None:
        return throttled

    run = CasePreflightRun(
        started_at=datetime.now(timezone.utc),
        trigger="web_manual",
        mode=mode,
        status=PREFLIGHT_STATUS_QUEUED,
        report_json={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(_execute_preflight, run.id, mode)
    logger.info("queued case preflight %s (mode=%s) by user %s", run.id, mode, current_user.email)

    return PreflightQueuedResponse(
        id=run.id,
        status=run.status,
        mode=mode,
        message="Preflight queued; poll /api/v1/system/case-preflight/latest for the result.",
    )


@router.get(
    "/case-preflight/{run_id}",
    response_model=PreflightRunSummary,
    summary="One case-file preflight run by id",
)
def get_case_preflight_run(run_id: str, db: Session = Depends(get_db)):
    _ensure_schema_if_missing(db)
    run = db.query(CasePreflightRun).filter(CasePreflightRun.id == run_id).one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preflight run {run_id} not found.",
        )
    return PreflightRunSummary(**run_summary(run, max_samples=settings.PREFLIGHT_MAX_SAMPLES))
