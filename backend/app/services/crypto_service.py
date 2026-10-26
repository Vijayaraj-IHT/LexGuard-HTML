import hashlib
import hmac
import secrets
from typing import Optional, List, Dict, Any
from app.core.config import settings

# Genesis hash for the initial block in the audit trail chain
GENESIS_HASH = "0" * 64


def compute_sha256(data: bytes) -> str:
    """Computes the SHA-256 hexadecimal digest for raw binary content."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest().lower()


def verify_sha256(data: bytes, expected_hash: str) -> bool:
    """Constant-time comparison of computed data hash against expected hash."""
    computed = compute_sha256(data)
    return hmac.compare_digest(computed.lower(), expected_hash.strip().lower())


def normalize_timestamp(ts: Any) -> str:
    """Normalizes any timestamp representation (datetime or str) to standard ISO seconds in UTC."""
    from datetime import timezone as _tz
    if hasattr(ts, "astimezone"):
        try:
            ts_utc = ts.astimezone(_tz.utc)
            return ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    s = str(ts).strip()
    return s.split(".")[0].split("+")[0].replace("Z", "").replace(" ", "T")


def compute_audit_log_hash(
    previous_hash: Optional[str],
    user_id: Optional[str],
    case_id: Optional[str],
    action: str,
    ip_address: Optional[str],
    timestamp_iso: Any,
    details: Optional[str] = None,
) -> str:
    """
    Computes cryptographic hash for an audit log record linking it to previous_hash.
    Implements a tamper-evident SHA-256 hash chain.
    """
    prev = previous_hash if previous_hash else GENESIS_HASH
    ts_norm = normalize_timestamp(timestamp_iso)
    payload = (
        f"{prev}|{user_id or ''}|{case_id or ''}|"
        f"{action}|{ip_address or ''}|{ts_norm}|{details or ''}"
    )
    return compute_sha256(payload.encode("utf-8"))


def _log_field(log: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(log, dict):
        return log.get(field_name, default)
    return getattr(log, field_name, default)


def _normalise_segment(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _verify_audit_segment(logs: List[Any], segment: int) -> Dict[str, Any]:
    expected_prev = GENESIS_HASH

    for index, log in enumerate(logs):
        log_prev = _log_field(log, "previous_log_hash") or GENESIS_HASH
        log_current = _log_field(log, "current_hash", "")
        log_ts = normalize_timestamp(_log_field(log, "timestamp"))

        if log_prev != expected_prev:
            return {
                "segment": segment,
                "is_valid": False,
                "total_records": len(logs),
                "broken_at_index": index,
                "broken_at_id": _log_field(log, "id", index),
                "reason": (
                    f"Chain link broken in segment {segment} at local record "
                    f"index {index}: previous hash does not match prior record."
                ),
                "message": (
                    f"Chain link broken in segment {segment} at local record "
                    f"index {index}."
                ),
            }

        recomputed = compute_audit_log_hash(
            previous_hash=log_prev,
            user_id=str(_log_field(log, "user_id", "") or ""),
            case_id=str(_log_field(log, "case_id", "") or ""),
            action=_log_field(log, "action", ""),
            ip_address=_log_field(log, "ip_address"),
            timestamp_iso=log_ts,
            details=_log_field(log, "details"),
        )

        if not hmac.compare_digest(recomputed, str(log_current)):
            return {
                "segment": segment,
                "is_valid": False,
                "total_records": len(logs),
                "broken_at_index": index,
                "broken_at_id": _log_field(log, "id", index),
                "reason": (
                    f"Content tampering detected in segment {segment} at record "
                    f"{_log_field(log, 'id', index)}: hash mismatch."
                ),
                "message": (
                    f"Content tampering detected in segment {segment} at local "
                    f"record index {index}."
                ),
            }

        expected_prev = log_current

    return {
        "segment": segment,
        "is_valid": True,
        "total_records": len(logs),
        "broken_at_index": None,
        "broken_at_id": None,
        "reason": None,
        "message": f"Audit segment {segment} verified successfully.",
    }


def verify_audit_chain(logs: List[Any]) -> Dict[str, Any]:
    """
    Verify hash-chained audit records segment by segment.

    ``is_valid`` describes the active (highest-numbered) segment. Archived
    segments are reported separately so an honestly resealed legacy chain
    remains visible instead of being presented as pristine. Records without
    ``seq``/``segment`` are treated as legacy segment 0 and retain their
    supplied order.
    """
    if not logs:
        return {
            "is_valid": True,
            "total_records": 0,
            "active_segment": None,
            "active_records": 0,
            "segments": [],
            "broken_at_index": None,
            "broken_at_id": None,
            "reason": None,
            "message": "No logs to verify",
        }

    def sort_key(indexed):
        index, log = indexed
        segment = _normalise_segment(_log_field(log, "segment", 0))
        seq_value = _log_field(log, "seq")
        try:
            seq = int(seq_value) if seq_value is not None else index
        except (TypeError, ValueError):
            seq = index
        return (segment, seq, index)

    ordered = [log for _, log in sorted(enumerate(logs), key=sort_key)]

    grouped: Dict[int, List[Any]] = {}
    for log in ordered:
        segment = _normalise_segment(_log_field(log, "segment", 0))
        grouped.setdefault(segment, []).append(log)

    segments = [
        _verify_audit_segment(grouped[segment], segment)
        for segment in sorted(grouped)
    ]
    active = segments[-1]
    archived_invalid = [
        result["segment"] for result in segments[:-1] if not result["is_valid"]
    ]

    if active["is_valid"]:
        message = (
            f"Active audit segment {active['segment']} intact: "
            f"{active['total_records']} records verified."
        )
        if archived_invalid:
            message += (
                " Archived segment(s) "
                + ", ".join(str(segment) for segment in archived_invalid)
                + " are invalid/superseded and retained for disclosure."
            )
        reason = None
    else:
        message = active["message"]
        reason = active["reason"]

    return {
        "is_valid": active["is_valid"],
        "total_records": len(ordered),
        "active_segment": active["segment"],
        "active_records": active["total_records"],
        "segments": segments,
        "broken_at_index": active["broken_at_index"],
        "broken_at_id": active["broken_at_id"],
        "reason": reason,
        "message": message,
    }


def generate_csrf_token() -> str:
    """Generates a secure cryptographically random CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, expected_token: str) -> bool:
    """Verifies CSRF token matching using constant time comparison."""
    if not token or not expected_token:
        return False
    return hmac.compare_digest(token, expected_token)
