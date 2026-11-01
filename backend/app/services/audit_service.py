import threading
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.services.crypto_service import compute_audit_log_hash, GENESIS_HASH

# Global mutex to prevent in-process thread-level race conditions on audit chain generation
_audit_lock = threading.Lock()


# AuditLog.id is a UUID string, so it carries NO insertion order. Timestamp is the
# only chronological ordering the ledger has; the id is used purely so that two rows
# sharing a timestamp still order identically on every read (a tie was previously
# resolved arbitrarily, which could make the chain look broken). Because the UUID
# tiebreak is arbitrary, it must never be used to decide which row came first —
# see check_audit_entry, which compares full-precision timestamps instead.
LEDGER_ORDER_DESC = (AuditLog.timestamp.desc(), AuditLog.id.desc())
LEDGER_ORDER_ASC = (AuditLog.timestamp.asc(), AuditLog.id.asc())


def latest_ledger_entry(db: Session, for_update: bool = False) -> Optional[AuditLog]:
    """The newest row by wall-clock timestamp, tie-broken deterministically by id."""
    query = db.query(AuditLog).order_by(*LEDGER_ORDER_DESC)
    if for_update and db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    return query.first()


def get_chain_head_hash(db: Session) -> str:
    """Returns the current_hash of the newest audit entry, or the genesis hash if the ledger is empty."""
    last_entry = latest_ledger_entry(db)
    return last_entry.current_hash if last_entry else GENESIS_HASH


def ledger_entries(db: Session) -> list:
    """Every audit row in chain order (timestamp asc, id asc tiebreak)."""
    return db.query(AuditLog).order_by(*LEDGER_ORDER_ASC).all()


def verify_ledger(db: Session) -> Dict[str, Any]:
    """
    Verifies the whole stored chain in append order.

    Use this (not a partial window) whenever a caller claims "the audit trail is
    intact" for a record; partial verification only proves the sampled rows.
    """
    from app.services.crypto_service import verify_audit_chain
    return verify_audit_chain(ledger_entries(db))


def build_audit_entry(
    previous_hash: Optional[str],
    *,
    action: str,
    user_id: Any = None,
    case_id: Any = None,
    ip_address: Optional[str] = None,
    details: Optional[str] = None,
    user_agent: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    The ONLY place that computes an audit-chain link. Every writer (ORM, raw SQL,
    scripts) must use it so that the hash covers exactly the values stored.

    Returns column values ready for insertion. `details` is hashed exactly as
    it is returned, so callers must not change it afterwards.
    """
    # Canonical storage form is aware UTC. SQLite drops tzinfo on write (it would store the
    # wall clock of a +05:30 value and read it back as UTC, breaking the hash), so we
    # convert BEFORE hashing and storing. Naive input is treated as UTC.
    ts = timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    prev = previous_hash or GENESIS_HASH
    uid = str(user_id) if user_id else None
    cid = str(case_id) if case_id else None
    current = compute_audit_log_hash(
        previous_hash=prev,
        user_id=uid,
        case_id=cid,
        action=action,
        ip_address=ip_address,
        timestamp_iso=ts,
        details=details,
    )
    return {
        "user_id": uid,
        "case_id": cid,
        "action": action,
        "details": details,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": ts,
        "previous_log_hash": prev,
        "current_hash": current,
    }


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
    Creates and commits an immutable, cryptographically hash-chained audit log entry.
    Links the new record's previous_log_hash to the current_hash of the most recent entry.
    Protected with thread mutex and row-level locking to prevent concurrency ledger forks.
    """
    with _audit_lock:
        # Retrieve the last record in the audit ledger with row lock if supported
        try:
            last_entry = latest_ledger_entry(db, for_update=True)
        except Exception:
            last_entry = db.query(AuditLog).order_by(*LEDGER_ORDER_DESC).first()

        previous_hash = last_entry.current_hash if last_entry else GENESIS_HASH
        entry = build_audit_entry(
            previous_hash,
            action=action,
            user_id=user_id,
            case_id=case_id,
            ip_address=ip_address,
            details=details,
            user_agent=user_agent,
        )

        log_entry = AuditLog(**entry)
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry


def _as_utc(timestamp) -> Optional[datetime]:
    """
    A comparable UTC datetime at FULL precision.

    Deliberately not ``normalize_timestamp``: that truncates to whole seconds for
    hashing, and second-truncated values cannot order two rows written in the same
    second (the UUID tiebreak is arbitrary, not chronological). Naive values are
    UTC by convention, matching the writer.
    """
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def check_audit_entry(db: Session, entry: AuditLog) -> Dict[str, bool]:
    """
    Local check of one audit entry:
    - recomputed_ok: its stored current_hash equals the hash recomputed from its own fields.
    - link_ok: its previous_log_hash is the genesis hash or the current_hash of some stored entry.

    This does NOT prove the whole chain is intact (that needs verify_audit_chain over
    every row). It proves that this entry was not edited, and that its parent exists.
    """
    from app.services.crypto_service import compute_audit_log_hash as _compute
    recomputed = _compute(
        previous_hash=entry.previous_log_hash,
        user_id=str(entry.user_id or ""),
        case_id=str(entry.case_id or ""),
        action=entry.action,
        ip_address=entry.ip_address,
        timestamp_iso=entry.timestamp,
        details=entry.details,
    )
    recomputed_ok = recomputed == entry.current_hash

    # Link check: the parent must exist, must not be this row, and must not sit in
    # the future. "exists somewhere" alone would accept a link pointing forward or
    # at itself, which is what a spliced or replayed row looks like.
    prev = entry.previous_log_hash or GENESIS_HASH
    if prev == GENESIS_HASH:
        link_ok = True
    else:
        parent = (
            db.query(AuditLog.id, AuditLog.timestamp)
            .filter(AuditLog.current_hash == prev)
            .order_by(*LEDGER_ORDER_ASC)
            .first()
        )
        if parent is None:
            link_ok = False
        else:
            link_ok = parent[0] != entry.id
            parent_ts, entry_ts = _as_utc(parent[1]), _as_utc(entry.timestamp)
            if link_ok and parent_ts is not None and entry_ts is not None:
                # Parent may share the child's timestamp (same-instant writes); it
                # may never sit strictly in the future.
                link_ok = parent_ts <= entry_ts
    return {"recomputed_ok": recomputed_ok, "link_ok": link_ok}
