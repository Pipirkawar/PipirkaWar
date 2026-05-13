"""FastAPI ``Depends`` helpers (Sprint 4.5-A, §5.2)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException, Request

from pipirik_wars.admin_web.auth.session import AdminSession
from pipirik_wars.admin_web.composition import AdminWebContainer


def get_container(request: Request) -> AdminWebContainer:
    container: AdminWebContainer = request.app.state.container
    return container


def get_session(request: Request) -> AdminSession | None:
    session: Any = getattr(request.state, "admin_session", None)
    if session is None:
        return None
    result: AdminSession = session
    return result


def require_session(request: Request) -> AdminSession:
    session = get_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def require_totp_verified(request: Request) -> AdminSession:
    session = require_session(request)
    container = get_container(request)
    if session.totp_verified_at is None:
        raise HTTPException(status_code=302, headers={"Location": "/totp"})
    ttl = container.settings.totp_verify_ttl_seconds
    if time.time() - session.totp_verified_at > ttl:
        raise HTTPException(status_code=302, headers={"Location": "/totp"})
    return session
