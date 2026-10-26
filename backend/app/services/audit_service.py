from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.crypto_service import GENESIS_HASH, compute_audit_log_hash

# Advisory-lock key used on PostgreSQL to serialise ledger appends. SQLite's
# database-level write lock already serialises writers for local/test use.
_AUDIT_CHAIN_LOCK_KEY = 72658391


def _lock_chain(db: Session) -> None:
    """Serialise the read-head -> compute-hash -> insert sequence."""
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _AUDIT_CHAIN_LOCK_KEY},
        )


def _last_entry(db: Session, segment: int) -> Optional[AuditLog]:
    query = (
        db.query(AuditLog)
        .filter(AuditLog.segment == segment)
        .order_by(
            AuditLog.seq.desc().nullslast(),
            AuditLog.timestamp.desc(),
            AuditLog.id.desc(),
        )
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    return query.first()


def _next_seq(db: Session) -> int:
    max_seq = db.query(func.max(AuditLog.seq)).scalar()
    if max_seq is not None:
        return int(max_seq) + 1
    # Pre-migration rows may all have NULL seq. Continue after their count so
    # the next append does not collide when seq is later backfilled.
    return int(db.query(func.count(AuditLog.id)).scalar() or 0) + 1


def _current_segment(db: Session) -> int:
    segment = db.query(func.max(AuditLog.segment)).scalar()
    # Segment 0 is reserved for restored, read-only legacy history. New
    # application writes always belong to segment 1 or later, even if an
    # operator starts the app before performing the explicit reseal.
    return max(1, int(segment)) if segment is not None else 1


def _append_audit_event(
    db: Session,
    *,
    segment: int,
    previous_hash: str,
    action: str,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    now = datetime.now(timezone.utc)
    current_hash = compute_audit_log_hash(
        previous_hash=previous_hash,
        user_id=str(user_id) if user_id else None,
        case_id=str(case_id) if case_id else None,
        action=action,
        ip_address=ip_address,
        timestamp_iso=now.isoformat(),
        details=details,
    )

    log_entry = AuditLog(
        user_id=user_id,
        case_id=case_id,
        action=action,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=now,
        seq=_next_seq(db),
        segment=segment,
        previous_log_hash=previous_hash,
        current_hash=current_hash,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry


def log_audit_event(
    db: Session,
    action: str,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Append one event through the application's only audit-chain writer.

    The transaction-level lock (PostgreSQL) and monotonic ``seq`` ensure two
    concurrent requests cannot both append to the same previous hash.
    """
    _lock_chain(db)
    segment = _current_segment(db)
    last_entry = _last_entry(db, segment)
    previous_hash = last_entry.current_hash if last_entry else GENESIS_HASH
    return _append_audit_event(
        db,
        segment=segment,
        previous_hash=previous_hash,
        action=action,
        user_id=user_id,
        case_id=case_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def reseal_audit_chain(
    db: Session,
    *,
    user_id: Optional[str] = None,
    reason: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Start a new, explicitly disclosed audit segment.

    Historical rows are never rewritten. The first row of the new segment
    records the archived segment, its size, its head hash and the operator's
    stated reason.
    """
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ValueError("A reseal reason of at least 10 characters is required")

    _lock_chain(db)
    archived_segment = db.query(func.max(AuditLog.segment)).scalar()
    if archived_segment is None:
        next_segment = 1
        details = f"Audit chain initialised in segment 1. Reason: {reason}"
    else:
        archived_segment = int(archived_segment)
        last_entry = _last_entry(db, archived_segment)
        archived_count = (
            db.query(func.count(AuditLog.id))
            .filter(AuditLog.segment == archived_segment)
            .scalar()
            or 0
        )
        archived_head = last_entry.current_hash if last_entry else GENESIS_HASH
        next_segment = archived_segment + 1
        details = (
            f"Audit chain segment {archived_segment} archived without rewriting "
            f"{archived_count} historical records; archived head hash "
            f"{archived_head}. New segment {next_segment} started. "
            f"Reason: {reason}"
        )

    return _append_audit_event(
        db,
        segment=next_segment,
        previous_hash=GENESIS_HASH,
        action="CHAIN_RESEALED",
        user_id=user_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
