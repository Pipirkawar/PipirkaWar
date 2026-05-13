"""Admin web panel entrypoint (Sprint 4.5-A, §A.6).

``create_app(settings)`` — FastAPI application factory.
``run()`` — console-script entrypoint (reads env, starts uvicorn).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.responses import Response

from pipirik_wars.admin_web.auth.csrf import CsrfMiddleware
from pipirik_wars.admin_web.auth.ip_allowlist import IpAllowlistMiddleware
from pipirik_wars.admin_web.auth.session import AdminSession
from pipirik_wars.admin_web.composition import AdminWebContainer, build_admin_web_container
from pipirik_wars.admin_web.routes import auth, dashboard, health, totp
from pipirik_wars.admin_web.settings import AdminWebSettings

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent


def _session_middleware(app: FastAPI, container: AdminWebContainer) -> None:
    """Inject AdminSession from cookie into ``request.state``."""

    @app.middleware("http")
    async def _load_session(request: Request, call_next: object) -> Response:
        _call_next: Callable[[Request], Coroutine[Any, Any, Response]] = call_next  # type: ignore[assignment]
        request.state.admin_session = None
        cookie = request.cookies.get("session")
        if cookie:
            try:
                session: AdminSession = container.session_manager.decode(cookie)
                request.state.admin_session = session
            except Exception:
                pass
        return await _call_next(request)


def _security_headers_middleware(app: FastAPI) -> None:
    """Add security response headers (CSP, X-Frame-Options, etc.)."""

    @app.middleware("http")
    async def _add_headers(request: Request, call_next: object) -> Response:
        _call_next: Callable[[Request], Coroutine[Any, Any, Response]] = call_next  # type: ignore[assignment]
        response: Response = await _call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "frame-src 'self' https://oauth.telegram.org;"
        )
        return response


def create_app(settings: AdminWebSettings | None = None) -> FastAPI:
    """Application factory."""
    if settings is None:
        settings = AdminWebSettings()  # type: ignore[call-arg]

    container = build_admin_web_container(settings)

    app = FastAPI(
        title="Pipirik Wars Admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.state.container = container

    templates_dir = _PACKAGE_DIR / "templates"
    app.state.templates = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )

    static_dir = _PACKAGE_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    _security_headers_middleware(app)
    _session_middleware(app, container)

    app.add_middleware(
        CsrfMiddleware,
    )
    app.add_middleware(
        IpAllowlistMiddleware,
        allowed_ips_raw=settings.allowed_ips,
        trust_proxy=settings.trust_proxy,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(totp.router)
    app.include_router(dashboard.router)

    return app


def run() -> None:
    """Console-script entrypoint: parse env + start uvicorn."""
    import uvicorn  # noqa: PLC0415

    settings = AdminWebSettings()  # type: ignore[call-arg]
    logger.info(
        "Starting admin web panel on %s:%s",
        settings.host,
        settings.port,
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
