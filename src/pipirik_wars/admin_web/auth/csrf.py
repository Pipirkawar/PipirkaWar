"""CSRF protection middleware (Sprint 4.5-A, §1.5).

Token lives inside the signed session cookie, verified on
mutating HTTP methods via ``X-CSRF-Token`` header or ``csrf_token`` form field.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pipirik_wars.admin_web.auth.session import AdminSession

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
EXEMPT_PATHS = frozenset({"/healthz", "/auth/telegram/callback"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests without a valid CSRF token."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        session: AdminSession | None = getattr(request.state, "admin_session", None)
        if session is None:
            return JSONResponse({"detail": "CSRF: no session"}, status_code=403)

        expected = session.csrf_token

        token = request.headers.get(CSRF_HEADER)
        if token is None:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                token = str(form.get(CSRF_FORM_FIELD, ""))
                request.state.form_cache = form

        if token is None or not secrets.compare_digest(token, expected):
            return JSONResponse({"detail": "CSRF token mismatch"}, status_code=403)

        return await call_next(request)


__all__ = ["CsrfMiddleware", "generate_csrf_token"]
