import time
from typing import Dict, List
from collections import defaultdict
import threading
from fastapi import Request, HTTPException, status

# In-memory sliding window rate limiter.
# Limits: per process (a multi-worker deployment has one limiter per worker), per client
# host (behind a reverse proxy every client shares the proxy IP), and never trusts
# X-Forwarded-For (that header is client-controlled).
_request_history: Dict[str, List[float]] = defaultdict(list)
# Sync dependencies run in FastAPI's thread pool; guard the shared dict.
_lock = threading.Lock()
_PRUNE_AFTER_KEYS = 5000
_STALE_AFTER_SECONDS = 3600  # longest window used by any endpoint is 60 s; keep a generous margin


def _prune(now: float) -> None:
    """Drop keys whose newest timestamp is stale, so memory stays bounded."""
    if len(_request_history) < _PRUNE_AFTER_KEYS:
        return
    cutoff = now - _STALE_AFTER_SECONDS
    for key in [k for k, v in _request_history.items() if not v or v[-1] < cutoff]:
        del _request_history[key]


def rate_limit(max_requests: int = 15, window_seconds: int = 60):
    """
    FastAPI dependency factory enforcing IP-based sliding window rate limiting.
    Provides immediate OWASP defense against brute force and credential stuffing.
    """
    def limiter_dependency(request: Request):
        with _lock:
            return _check(request)

    def _check(request: Request):
        client_ip = request.client.host if request.client else "127.0.0.1"
        endpoint = request.url.path
        key = f"{client_ip}:{endpoint}"
        now = time.time()
        cutoff = now - window_seconds
        _prune(now)

        # Clean old timestamps
        timestamps = [ts for ts in _request_history[key] if ts > cutoff]
        if len(timestamps) >= max_requests:
            retry_after = int(window_seconds - (now - timestamps[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {max(1, retry_after)} seconds before trying again.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        timestamps.append(now)
        _request_history[key] = timestamps
        return True

    return limiter_dependency
