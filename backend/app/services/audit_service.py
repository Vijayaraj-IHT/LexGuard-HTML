import threading
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.services.crypto_service import compute_audit_log_hash, GENESIS_HASH

# Global mutex to prevent in-process thread-level race conditions on audit chain generation
_audit_lock = threading.Lock()


def get_chain_head_hash(db: Session) -> str:
    """Returns the current_hash of the newest audit entry, or the genesis hash if the ledger is empty."""
    last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
    return last_entry.current_hash if last_entry else GENESIS_HASH


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
            if db.bind and db.bind.dialect.name == "postgresql":
                last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).with_for_update().first()
            else:
                last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        except Exception:
            last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()

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
    prev = entry.previous_log_hash or GENESIS_HASH
    link_ok = prev == GENESIS_HASH or (
        db.query(AuditLog.id).filter(AuditLog.current_hash == prev).first() is not None
    )
    return {"recomputed_ok": recomputed_ok, "link_ok": link_ok}
