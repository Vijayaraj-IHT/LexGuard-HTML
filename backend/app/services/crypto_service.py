import hashlib
import hmac
import secrets
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.core.config import settings

# Genesis hash for the initial block in the audit trail chain
GENESIS_HASH = "0" * 64



def compute_sha256(data: bytes) -> str:
    """Computes the SHA-256 hexadecimal digest for raw binary content."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest().lower()


def compute_sha256_stream(file_path_or_stream: Any, chunk_size: int = 65536) -> str:
    """
    Computes SHA-256 in chunks, reading the bytes every time.

    No digest cache: a cache keyed on (path, mtime, size) was shown to accept a
    same-size tampered file whose mtime had been restored with os.utime().
    Integrity checks must always re-read the content.
    """
    if isinstance(file_path_or_stream, (str, Path)):
        p = Path(file_path_or_stream)
        if p.exists():
            hasher = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest().lower()

    # If stream / file-like object
    hasher = hashlib.sha256()
    if hasattr(file_path_or_stream, "read"):
        while chunk := file_path_or_stream.read(chunk_size):
            hasher.update(chunk)
        return hasher.hexdigest().lower()

    if isinstance(file_path_or_stream, (bytes, bytearray)):
        return compute_sha256(file_path_or_stream)

    raise ValueError("Unsupported input for compute_sha256_stream")


def verify_sha256(data: bytes, expected_hash: str) -> bool:
    """Constant-time comparison of computed data hash against expected hash."""
    computed = compute_sha256(data)
    return hmac.compare_digest(computed.lower(), expected_hash.strip().lower())


def verify_sha256_stream(file_path_or_stream: Any, expected_hash: str, chunk_size: int = 65536) -> bool:
    """Constant-time verification of chunk-computed stream hash against expected digest."""
    computed = compute_sha256_stream(file_path_or_stream, chunk_size=chunk_size)
    return hmac.compare_digest(computed.lower(), expected_hash.strip().lower())


def normalize_timestamp(ts: Any) -> str:
    """
    Normalizes any timestamp representation to ISO seconds in UTC.

    Convention (fixes a timezone-dependent verification bug): a timezone-naive
    value is interpreted as UTC. Previously it was interpreted as the server's
    local time, so the same audit chain verified differently on different
    machines (measured: 720 vs 755 mismatches under TZ=UTC vs Asia/Kolkata).
    """
    from datetime import datetime as _dt, timezone as _tz
    if isinstance(ts, _dt):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_tz.utc)
        return ts.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    s = str(ts).strip()
    # Parse offset-aware ISO strings properly (the old code dropped the offset).
    try:
        parsed = _dt.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
        return normalize_timestamp(parsed)
    except ValueError:
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
    Implements a tamper-evident blockchain-style hash chain.
    """
    prev = previous_hash if previous_hash else GENESIS_HASH
    ts_norm = normalize_timestamp(timestamp_iso)
    payload = (
        f"{prev}|{user_id or ''}|{case_id or ''}|"
        f"{action}|{ip_address or ''}|{ts_norm}|{details or ''}"
    )
    return compute_sha256(payload.encode("utf-8"))


def verify_audit_chain(logs: List[Any]) -> Dict[str, Any]:
    """
    Verifies the integrity of a chronological sequence of audit log entries.
    Returns validation status and reports any broken link or altered record.
    """
    if not logs:
        return {"is_valid": True, "total_records": 0, "broken_at_id": None, "message": "No logs to verify"}

    expected_prev = GENESIS_HASH

    for index, log in enumerate(logs):
        log_prev = getattr(log, "previous_log_hash", None) or GENESIS_HASH
        log_current = getattr(log, "current_hash", "")
        log_ts = normalize_timestamp(log.timestamp)

        # Check chain continuity
        if log_prev != expected_prev:
            return {
                "is_valid": False,
                "total_records": len(logs),
                "broken_at_id": getattr(log, "id", index),
                "reason": f"Chain link broken at record index {index}: previous hash does not match prior record.",
            }

        # Check hash recalculation match
        recomputed = compute_audit_log_hash(
            previous_hash=log_prev,
            user_id=str(getattr(log, "user_id", "") or ""),
            case_id=str(getattr(log, "case_id", "") or ""),
            action=getattr(log, "action", ""),
            ip_address=getattr(log, "ip_address", None),
            timestamp_iso=log_ts,
            details=getattr(log, "details", None),
        )

        if not hmac.compare_digest(recomputed, log_current):
            return {
                "is_valid": False,
                "total_records": len(logs),
                "broken_at_id": getattr(log, "id", index),
                "reason": f"Content tampering detected at record {getattr(log, 'id', index)}: hash mismatch.",
            }

        expected_prev = log_current

    return {
        "is_valid": True,
        "total_records": len(logs),
        "broken_at_id": None,
        "message": "All audit trail records are cryptographically verified and intact.",
    }


def compute_h_meta(case_no: Any, court: Any, judge: Any, disposition: Any, year: Any) -> str:
    """H_meta = SHA-256(case_no|court|judge|disposition|year). Format is part of the sealed record."""
    meta_str = f"{case_no}|{court}|{judge or ''}|{disposition or ''}|{year}"
    return hashlib.sha256(meta_str.encode("utf-8")).hexdigest()


def compute_h_text(full_text: Optional[str]) -> str:
    """H_text = SHA-256(full_text). A missing text hashes the empty string (flagged elsewhere)."""
    return hashlib.sha256((full_text or "").encode("utf-8")).hexdigest()


def compute_judicial_seal(h_doc: str, h_meta: str, h_text: str, approved_at_iso: str) -> str:
    """
    Composite judicial seal Phi_case = SHA-256(H_doc | H_meta | H_text | T_approved).

    The formula is frozen: changing it would invalidate every seal already
    issued. Callers must pass T_approved exactly as `datetime.isoformat()`
    produced it at approval time.
    """
    payload = f"{h_doc}|{h_meta}|{h_text}|{approved_at_iso}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generates a secure cryptographically random CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, expected_token: str) -> bool:
    """Verifies CSRF token matching using constant time comparison."""
    if not token or not expected_token:
        return False
    return hmac.compare_digest(token, expected_token)
