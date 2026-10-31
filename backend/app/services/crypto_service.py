import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Genesis hash for the initial block in the audit trail chain
GENESIS_HASH = "0" * 64

# In-memory mtime/size cache: (canonical_path, mtime_ns, size_bytes) -> sha256_hex
_file_hash_cache: Dict[Tuple[str, int, int], str] = {}


def compute_sha256(data: bytes) -> str:
    """Computes the SHA-256 hexadecimal digest for raw binary content."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest().lower()


def compute_sha256_stream(file_path_or_stream: Any, chunk_size: int = 65536) -> str:
    """Computes SHA-256 in 64 KB chunks, using in-memory stat cache if a path is provided."""
    if isinstance(file_path_or_stream, (str, Path)):
        p = Path(file_path_or_stream)
        if p.exists():
            st = p.stat()
            cache_key = (str(p.resolve()), st.st_mtime_ns, st.st_size)
            if cache_key in _file_hash_cache:
                return _file_hash_cache[cache_key]

            hasher = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            digest = hasher.hexdigest().lower()
            _file_hash_cache[cache_key] = digest
            return digest

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


def generate_csrf_token() -> str:
    """Generates a secure cryptographically random CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, expected_token: str) -> bool:
    """Verifies CSRF token matching using constant time comparison."""
    if not token or not expected_token:
        return False
    return hmac.compare_digest(token, expected_token)
