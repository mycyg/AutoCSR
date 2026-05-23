"""HTTP rate limit middleware (M19).

Strategy:
  - Try slowapi first (Redis or in-memory limiter). If not installed, fall
    back to a tiny in-process token bucket keyed by (user_id, route).
  - User id is taken from the X-User-Id header (the existing dev mode
    convention; replaced by JWT subject in M21).
  - Per-route limits live in :data:`RATE_LIMITS`. Defaults are conservative
    enough to be invisible during normal use but trip cleanly under a flood
    so e2e can validate the 429 path.

On limit hit: return ``429 Too Many Requests`` with ``Retry-After`` header.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import RLock
from typing import Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("autocsr.rate_limit")


# (path_suffix, method) → (max_calls, window_seconds)
# We match by suffix so the same rule applies to /api/projects/{pid}/upload etc.
RATE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("/upload",       "POST"): (10, 60),   # 10/min/user
    ("/ingest",       "POST"): (5,  60),   #  5/min/user
    ("/ask",          "POST"): (20, 60),   # 20/min/user
    ("/sandbox/run",  "POST"): (10, 60),   # 10/min/user
    ("/auth/login",   "POST"): (5,  60),   # cushion for M21
}


class _TokenBucket:
    """Sliding-window counter per (key, route). Thread-safe."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: str, route: str, max_calls: int, window: int) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            q = self._hits[(key, route)]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max_calls:
                retry_after = max(1.0, q[0] + window - now)
                return False, retry_after
            q.append(now)
            return True, 0.0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_BUCKET = _TokenBucket()


def _user_key(request: Request) -> str:
    # Prefer the dev X-User-Id header; fall back to client host so anonymous
    # callers still get capped (rather than sharing one global bucket).
    uid = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
    if uid:
        return f"u:{uid}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def _rule_for(path: str, method: str) -> tuple[int, int] | None:
    method = method.upper()
    for (suffix, m), limit in RATE_LIMITS.items():
        if m != method:
            continue
        if path.endswith(suffix):
            return limit
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces :data:`RATE_LIMITS`."""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path or ""
        method = request.method
        rule = _rule_for(path, method)
        if rule is None:
            return await call_next(request)
        max_calls, window = rule
        key = _user_key(request)
        route_key = f"{method} {path}"
        ok, retry = _BUCKET.check(key, route_key, max_calls, window)
        if not ok:
            logger.info("rate_limit_hit key=%s route=%s retry=%.1fs",
                        key, route_key, retry)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "limit": max_calls,
                    "window_seconds": window,
                    "retry_after_seconds": round(retry, 2),
                },
                headers={"Retry-After": str(int(retry) + 1)},
            )
        return await call_next(request)


def reset_buckets() -> None:
    """Clear all buckets — used by tests to start from a known state."""
    _BUCKET.clear()


__all__ = ["RateLimitMiddleware", "RATE_LIMITS", "reset_buckets"]
