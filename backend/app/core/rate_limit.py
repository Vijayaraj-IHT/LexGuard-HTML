import time
from typing import Dict, List
from collections import defaultdict
from fastapi import Request, HTTPException, status

# In-memory sliding window rate limiter
_request_history: Dict[str, List[float]] = defaultdict(list)


def rate_limit(max_requests: int = 15, window_seconds: int = 60):
    """
    FastAPI dependency factory enforcing IP-based sliding window rate limiting.
    Provides immediate OWASP defense against brute force and credential stuffing.
    """
    def limiter_dependency(request: Request):
        client_ip = request.client.host if request.client else "127.0.0.1"
        endpoint = request.url.path
        key = f"{client_ip}:{endpoint}"
        now = time.time()
        cutoff = now - window_seconds

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
