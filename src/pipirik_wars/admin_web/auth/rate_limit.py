"""In-memory rate-limiting middleware for auth endpoints (Sprint 4.5-H, §4.5.9).

Sliding-window counter per client IP.  Designed for single-process
deployments (typical for an internal admin panel behind IP allowlist).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMIT_PATHS = frozenset(
    {
        "/auth/telegram/callback",
        "/totp/verify",
        "/totp/setup",
    }
)


class _SlidingWindow:
    """Sliding-window counter for a single key."""

    __slots__ = ("_hits", "_window_seconds")

    def __init__(self, window_seconds: float) -> None:
        self._window_seconds = window_seconds
        self._hits: list[float] = []

    def hit(self, now: float) -> int:
        cutoff = now - self._window_seconds
        self._hits = [t for t in self._hits if t > cutoff]
        self._hits.append(now)
        return len(self._hits)

    def current_count(self, now: float) -> int:
        cutoff = now - self._window_seconds
        self._hits = [t for t in self._hits if t > cutoff]
        return len(self._hits)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit requests to sensitive auth endpoints by client IP."""

    def __init__(
        self,
        app: Any,
        *,
        max_requests: int = 10,
        window_seconds: int = 60,
        rate_limit_paths: frozenset[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._rate_limit_paths = rate_limit_paths or _DEFAULT_RATE_LIMIT_PATHS
        self._buckets: dict[str, _SlidingWindow] = {}

    def _get_client_ip(self, request: Request) -> str:
        return request.client.host if request.client else "0.0.0.0"

    def _cleanup_stale(self, now: float) -> None:
        stale_keys = [k for k, window in self._buckets.items() if window.current_count(now) == 0]
        for k in stale_keys:
            del self._buckets[k]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path not in self._rate_limit_paths:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        if len(self._buckets) > 10_000:
            self._cleanup_stale(now)

        if client_ip not in self._buckets:
            self._buckets[client_ip] = _SlidingWindow(float(self._window_seconds))

        count = self._buckets[client_ip].hit(now)

        if count > self._max_requests:
            retry_after = str(self._window_seconds)
            logger.warning(
                "rate_limit.exceeded client_ip=%s path=%s count=%d",
                client_ip,
                request.url.path,
                count,
            )
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": retry_after},
            )

        return await call_next(request)


__all__ = ["RateLimitMiddleware"]
