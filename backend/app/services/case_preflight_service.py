"""Case-file preflight: verify (and optionally repair) the stored corpus.

What a run checks, per case:

* ``missing``      — the ``file_path`` does not resolve to a readable file on disk.
* ``mismatch``     — the file exists but its SHA-256 does not equal ``file_hash``.
* ``invalid_metadata`` — required metadata is absent or self-contradictory
  (missing case_no/title/court/year, impossible year, or a year that disagrees with
  the year embedded in the case number).
* ``duplicate_hash_count`` — cases that share a ``file_hash`` with another case.

A case is counted in ``verified_count`` only when it has no missing file, no hash
mismatch and no invalid metadata. ``duplicate_hash_count`` is informational and
overlaps the other buckets.

PostgreSQL is required in production because the run is serialised with a session
advisory lock. SQLite runs are refused unless ``allow_non_postgres=True`` is passed
(CLI: ``--allow-sqlite``, tests), in which case no lock is taken — SQLite has no
server-side advisory locks to take.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import resolve_case_pdf_path, settings
from app.models.case import Case
from app.models.preflight import (
    PREFLIGHT_ACTIVE_STATUSES,
    PREFLIGHT_STATUS_BUSY,
    PREFLIGHT_STATUS_COMPLETED,
    PREFLIGHT_STATUS_FAILED,
    PREFLIGHT_STATUS_ISSUES,
    PREFLIGHT_STATUS_POSTGRES_REQUIRED,
    PREFLIGHT_STATUS_REPAIRED,
    PREFLIGHT_STATUS_RUNNING,
    CasePreflightRun,
)
from app.services.crypto_service import compute_sha256_stream

logger = logging.getLogger(__name__)

#: Advisory-lock key used to serialise preflight runs. Configurable via
#: ``PREFLIGHT_ADVISORY_LOCK_ID`` but must stay stable across processes.
DEFAULT_LOCK_ID = 728311

#: Indexes the cases table is expected to carry (name -> column).
CASE_INDEXES: Dict[str, str] = {
    "ix_cases_file_hash": "file_hash",
    "ix_cases_cnr_number": "cnr_number",
    "ix_cases_decision_date": "decision_date",
    "ix_cases_status": "status",
}

MAX_SAMPLES_DEFAULT = 25

_PLACEHOLDER_JUDGE = re.compile(r"hon'?ble\s+(bench|court)", re.IGNORECASE)
_YEAR_IN_CASE_NO = re.compile(r"\b(19|20)\d{2}\b")
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/[\w.\-]+/[\w.\-/]+|\\\\)")


# --------------------------------------------------------------------------- dialect
def dialect_name(db: Session) -> str:
    """Return the engine dialect name for this session (``postgresql``/``sqlite``)."""
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    dialect = getattr(bind, "dialect", None)
    if dialect is not None:
        return dialect.name
    return "unknown"


def is_postgres(db: Session) -> bool:
    return dialect_name(db) == "postgresql"


def lock_id() -> int:
    return int(getattr(settings, "PREFLIGHT_ADVISORY_LOCK_ID", DEFAULT_LOCK_ID))


# --------------------------------------------------------------------------- schema
def ensure_case_indexes(bind: Engine) -> List[str]:
    """Create the four required cases indexes when absent. Returns the names created."""
    created: List[str] = []
    inspector = inspect(bind)
    if not inspector.has_table("cases"):
        return created
    existing = {ix.get("name") for ix in inspector.get_indexes("cases")}
    with bind.begin() as conn:
        for name, column in CASE_INDEXES.items():
            if name in existing:
                continue
            # IF NOT EXISTS keeps this safe to re-run on both backends.
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON cases ({column})"))
            created.append(name)
    return created


def ensure_preflight_schema(bind: Engine) -> Dict[str, Any]:
    """Create ``case_preflight_runs`` and the cases indexes if they are missing."""
    table_created = False
    inspector = inspect(bind)
    if not inspector.has_table(CasePreflightRun.__tablename__):
        CasePreflightRun.__table__.create(bind=bind, checkfirst=True)
        table_created = True
    indexes = ensure_case_indexes(bind)
    return {
        "table_created": table_created,
        "indexes_created": indexes,
        "dialect": bind.dialect.name,
    }


# --------------------------------------------------------------------------- locking
def _try_advisory_lock(db: Session, key: int) -> bool:
    """Try to take a session-level PostgreSQL advisory lock. Never raises."""
    try:
        return bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("advisory lock acquisition failed: %s", exc)
        db.rollback()
        return False


def _release_advisory_lock(db: Session, key: int) -> None:
    try:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("advisory lock release failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


# --------------------------------------------------------------------------- helpers
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _case_year_from_case_no(case_no: Optional[str]) -> Optional[int]:
    if not case_no:
        return None
    matches = _YEAR_IN_CASE_NO.findall(case_no)
    if not matches:
        return None
    # Last 4-digit year in the string is the filing/decision year in Indian cause titles.
    years = [int(m) for m in re.findall(r"\b(?:19|20)\d{2}\b", case_no)]
    return years[-1] if years else None


def invalid_metadata_reasons(case: Case) -> List[str]:
    """Return the structural metadata problems for one case (empty list = valid)."""
    reasons: List[str] = []
    if not (case.case_no or "").strip():
        reasons.append("missing_case_no")
    if not (case.title or "").strip():
        reasons.append("missing_title")
    if not (case.court or "").strip():
        reasons.append("missing_court")
    if case.year is None:
        reasons.append("missing_year")
    elif not (1900 <= int(case.year) <= 2100):
        reasons.append("impossible_year")
    else:
        embedded = _case_year_from_case_no(case.case_no)
        if embedded is not None and abs(int(case.year) - embedded) > 1:
            reasons.append("year_conflicts_with_case_no")
    return reasons


def _resolve_existing_pdf(file_path: Optional[str]) -> Optional[str]:
    if not file_path:
        return None
    try:
        path = resolve_case_pdf_path(file_path)
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        return str(path) if path.is_file() else None
    except OSError:
        return None


def sanitize_report(report: Optional[Dict[str, Any]], max_samples: int = MAX_SAMPLES_DEFAULT) -> Dict[str, Any]:
    """Strip anything path-like and cap sample lists before a report leaves the server."""
    if not isinstance(report, dict):
        return {}

    def clean(value: Any, depth: int = 0) -> Any:
        if depth > 4:
            return None
        if isinstance(value, dict):
            return {str(k): clean(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v, depth + 1) for v in value[:max_samples]]
        if isinstance(value, str):
            return _ABSOLUTE_PATH.sub("<redacted-path>", value)[:500]
        return value

    cleaned = clean(report)
    return cleaned if isinstance(cleaned, dict) else {}


def _duplicate_hashes(db: Session) -> Dict[str, int]:
    """Map of file_hash -> number of cases, for hashes shared by more than one case."""
    rows = (
        db.query(Case.file_hash, func.count(Case.id))
        .filter(Case.file_hash.isnot(None))
        .group_by(Case.file_hash)
        .having(func.count(Case.id) > 1)
        .all()
    )
    return {row[0]: int(row[1]) for row in rows}


def latest_run(db: Session) -> Optional[CasePreflightRun]:
    return db.query(CasePreflightRun).order_by(CasePreflightRun.started_at.desc()).first()


def _active_run(db: Session) -> Optional[CasePreflightRun]:
    return (
        db.query(CasePreflightRun)
        .filter(CasePreflightRun.status.in_(PREFLIGHT_ACTIVE_STATUSES))
        .order_by(CasePreflightRun.started_at.desc())
        .first()
    )


def _batched_cases(db: Session, batch_size: int) -> Iterable[List[Case]]:
    last_id: Optional[str] = None
    while True:
        query = db.query(Case).order_by(Case.id)
        if last_id is not None:
            query = query.filter(Case.id > last_id)
        batch = query.limit(batch_size).all()
        if not batch:
            return
        yield batch
        last_id = batch[-1].id


def _new_run(
    db: Session, mode: str, trigger: str, run: Optional[CasePreflightRun] = None
) -> CasePreflightRun:
    """Create the run row, or claim a QUEUED row handed over by a background task."""
    if run is not None:
        run.mode = (mode or "verify")[:20]
        run.trigger = (trigger or run.trigger or "web_init")[:50]
        run.status = PREFLIGHT_STATUS_RUNNING
        run.started_at = _utcnow()
        run.finished_at = None
        db.merge(run)
        db.commit()
        db.refresh(run)
        return run

    run = CasePreflightRun(
        started_at=_utcnow(),
        trigger=(trigger or "web_init")[:50],
        mode=(mode or "verify")[:20],
        status=PREFLIGHT_STATUS_RUNNING,
        report_json={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# --------------------------------------------------------------------------- main entry
def run_case_preflight(
    db: Session,
    mode: str = "verify",
    trigger: str = "web_init",
    batch_size: int = 500,
    allow_non_postgres: bool = False,
    quarantine_mismatch: bool = False,
    verify_hashes: bool = True,
    run: Optional[CasePreflightRun] = None,
) -> CasePreflightRun:
    """Verify the corpus and record the outcome in ``case_preflight_runs``.

    Returns the persisted run row; inspect ``run.status`` for the outcome. The
    function does not raise on refusal (POSTGRES_REQUIRED / BUSY) so callers can map
    the status to an HTTP code or an exit code.

    ``run`` lets a background task hand over a QUEUED row it created up-front, so the
    API can return a run id before the work starts.
    """
    mode = (mode or "verify").lower()
    if mode not in ("verify", "repair"):
        raise ValueError(f"unsupported preflight mode: {mode!r} (expected 'verify' or 'repair')")
    batch_size = max(1, min(int(batch_size or 500), 5000))

    run = _new_run(db, mode=mode, trigger=trigger, run=run)
    started = time.perf_counter()

    if not is_postgres(db) and not allow_non_postgres:
        run.status = PREFLIGHT_STATUS_POSTGRES_REQUIRED
        run.finished_at = _utcnow()
        run.report_json = {
            "message": (
                "Case preflight requires PostgreSQL for advisory locking. "
                "Re-run with --allow-sqlite (CLI) or allow_non_postgres=True (service) "
                "for local evaluation."
            ),
            "dialect": dialect_name(db),
            "mode": mode,
            "trigger": run.trigger,
            "advisory_lock": {"id": lock_id(), "held": False},
        }
        db.commit()
        db.refresh(run)
        logger.info("preflight refused: PostgreSQL required (dialect=%s)", dialect_name(db))
        return run

    key = lock_id()
    postgres = is_postgres(db)
    locked = False
    if postgres:
        locked = _try_advisory_lock(db, key)
        if not locked:
            run.status = PREFLIGHT_STATUS_BUSY
            run.finished_at = _utcnow()
            run.report_json = {
                "message": "Another preflight run holds the advisory lock; skipped.",
                "dialect": dialect_name(db),
                "mode": mode,
                "trigger": run.trigger,
                "advisory_lock": {"id": key, "held": False},
            }
            db.commit()
            db.refresh(run)
            return run

    samples: Dict[str, List[str]] = {"missing": [], "mismatch": [], "invalid_metadata": [], "duplicate_hash": []}
    reasons_seen: Dict[str, int] = {}
    max_samples = int(getattr(settings, "PREFLIGHT_MAX_SAMPLES", MAX_SAMPLES_DEFAULT))
    quarantined: List[str] = []

    try:
        duplicates = _duplicate_hashes(db)
        duplicate_case_ids = set()
        if duplicates:
            for (case_id,) in (
                db.query(Case.id).filter(Case.file_hash.in_(list(duplicates.keys()))).all()
            ):
                duplicate_case_ids.add(case_id)

        total = verified = missing = mismatch = invalid = 0
        duplicate_cases = 0

        for batch in _batched_cases(db, batch_size):
            for case in batch:
                total += 1

                reasons = invalid_metadata_reasons(case)
                if reasons:
                    invalid += 1
                    for reason in reasons:
                        reasons_seen[reason] = reasons_seen.get(reason, 0) + 1
                    if len(samples["invalid_metadata"]) < max_samples:
                        samples["invalid_metadata"].append(case.id)

                path = _resolve_existing_pdf(case.file_path)
                file_ok = True
                if path is None:
                    missing += 1
                    file_ok = False
                    if len(samples["missing"]) < max_samples:
                        samples["missing"].append(case.id)
                elif verify_hashes:
                    try:
                        actual = compute_sha256_stream(path)
                    except OSError as exc:
                        logger.warning("cannot read %s: %s", case.id, exc)
                        actual = None
                    if actual and case.file_hash and actual != case.file_hash:
                        mismatch += 1
                        file_ok = False
                        if len(samples["mismatch"]) < max_samples:
                            samples["mismatch"].append(case.id)
                        if mode == "repair" and quarantine_mismatch:
                            if (case.status or "").lower() != "quarantined":
                                case.status = "quarantined"
                                quarantined.append(case.id)

                if case.id in duplicate_case_ids:
                    duplicate_cases += 1
                    if len(samples["duplicate_hash"]) < max_samples:
                        samples["duplicate_hash"].append(case.id)

                if file_ok and not reasons:
                    verified += 1

            if mode == "repair":
                db.commit()

        finished = _utcnow()
        has_issues = bool(missing or mismatch or invalid or duplicate_cases)
        if mode == "repair" and quarantined:
            run.status = PREFLIGHT_STATUS_REPAIRED
        else:
            run.status = PREFLIGHT_STATUS_ISSUES if has_issues else PREFLIGHT_STATUS_COMPLETED

        run.total_cases = total
        run.verified_count = verified
        run.missing_count = missing
        run.mismatch_count = mismatch
        run.duplicate_hash_count = duplicate_cases
        run.invalid_metadata_count = invalid
        run.finished_at = finished
        run.report_json = {
            "dialect": dialect_name(db),
            "mode": mode,
            "trigger": run.trigger,
            "batch_size": batch_size,
            "verify_hashes": bool(verify_hashes),
            "advisory_lock": {"id": key, "held": locked},
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "counts": {
                "total_cases": total,
                "verified": verified,
                "missing": missing,
                "mismatch": mismatch,
                "invalid_metadata": invalid,
                "duplicate_hash": duplicate_cases,
            },
            "metadata_reasons": dict(sorted(reasons_seen.items())),
            "duplicates": {"hashes": len(duplicates), "cases": duplicate_cases},
            "repair": {
                "requested": mode == "repair",
                "quarantine_mismatch": bool(quarantine_mismatch),
                "quarantined": quarantined[:max_samples],
                "quarantined_count": len(quarantined),
            },
            "samples": samples,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(finished),
        }
        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:  # pragma: no cover - defensive path
        db.rollback()
        logger.exception("case preflight failed")
        run = db.query(CasePreflightRun).filter(CasePreflightRun.id == run.id).one_or_none() or run
        run.status = PREFLIGHT_STATUS_FAILED
        run.finished_at = _utcnow()
        run.report_json = {
            "dialect": dialect_name(db),
            "mode": mode,
            "trigger": run.trigger,
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "advisory_lock": {"id": key, "held": locked},
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
        }
        db.commit()
        db.refresh(run)
        return run

    finally:
        if locked:
            _release_advisory_lock(db, key)


def run_summary(run: CasePreflightRun, max_samples: int = MAX_SAMPLES_DEFAULT) -> Dict[str, Any]:
    """Public, path-free representation of a run (used by CLI output and endpoints)."""
    return {
        "id": run.id,
        "status": run.status,
        "mode": run.mode,
        "trigger": run.trigger,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "total_cases": run.total_cases,
        "verified_count": run.verified_count,
        "missing_count": run.missing_count,
        "mismatch_count": run.mismatch_count,
        "duplicate_hash_count": run.duplicate_hash_count,
        "invalid_metadata_count": run.invalid_metadata_count,
        "report": sanitize_report(run.report_json, max_samples=max_samples),
    }
