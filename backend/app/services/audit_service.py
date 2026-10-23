from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.services.crypto_service import compute_audit_log_hash, GENESIS_HASH


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
    """
    # Retrieve the last record in the audit ledger
    last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
    previous_hash = last_entry.current_hash if last_entry else GENESIS_HASH

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
        previous_log_hash=previous_hash,
        current_hash=current_hash,
    )

    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry
