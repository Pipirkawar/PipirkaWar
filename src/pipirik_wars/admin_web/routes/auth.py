"""Auth routes: login page, TG callback, logout (Sprint 4.5-A, §3.1–3.2, §3.7)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pipirik_wars.admin_web.auth.csrf import generate_csrf_token
from pipirik_wars.admin_web.auth.session import AdminSession
from pipirik_wars.admin_web.auth.telegram_login import (
    InvalidLoginHashError,
    StaleLoginError,
    verify_telegram_login,
)
from pipirik_wars.admin_web.deps import get_container, get_session
from pipirik_wars.domain.admin.ports.admin_audit import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
)
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.services.admin_audit import SqlAlchemyAdminAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    container = get_container(request)
    session = get_session(request)

    if session is not None and session.totp_verified_at is not None:
        ttl = container.settings.totp_verify_ttl_seconds
        if time.time() - session.totp_verified_at <= ttl:
            return RedirectResponse(url="/dashboard", status_code=302)

    templates = request.app.state.templates
    content: str = templates.get_template("login.html").render(
        bot_username=container.bot_username,
        request=request,
    )
    return HTMLResponse(content=content)


@router.post("/auth/telegram/callback")
async def telegram_callback(request: Request) -> JSONResponse | RedirectResponse:
    container = get_container(request)
    body = await request.json()
    data: dict[str, str | int] = body

    try:
        login_data = verify_telegram_login(
            data=data,
            bot_token=container.bot_token,
        )
    except InvalidLoginHashError:
        logger.warning("auth.tg_login.hmac_mismatch")
        return JSONResponse({"detail": "Invalid login hash"}, status_code=401)
    except StaleLoginError:
        logger.warning("auth.tg_login.stale")
        return JSONResponse({"detail": "Login data expired"}, status_code=401)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(login_data.id)

        if admin is None or not admin.is_active:
            audit = SqlAlchemyAdminAuditLogger(uow=uow)
            await audit.record(
                AdminAuditEntry(
                    admin_id=admin.id if admin and admin.id is not None else 0,
                    action=AdminAuditAction.ADMIN_AUTHORIZATION_DENIED,
                    target_kind="admin",
                    target_id=str(login_data.id),
                    before=None,
                    after=None,
                    reason=f"TG Login denied: admin {'inactive' if admin else 'not found'}",
                    idempotency_key=None,
                    source=AdminAuditSource.WEB,
                    tg_chat_id=None,
                    ip=request.client.host if request.client else None,
                    occurred_at=container.clock.now(),
                ),
            )
            await uow.commit()
            logger.warning("auth.tg_login.inactive_admin tg_id=%s", login_data.id)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    admin_id = admin.id
    if admin_id is None:  # pragma: no cover
        return JSONResponse({"detail": "Server error"}, status_code=500)

    session = AdminSession(
        admin_id=admin_id,
        tg_username=login_data.username,
        totp_verified_at=None,
        csrf_token=generate_csrf_token(),
    )

    cookie_value = container.session_manager.encode(session)
    response = JSONResponse({"redirect": "/totp"}, status_code=200)
    response.set_cookie(
        key="session",
        value=cookie_value,
        max_age=container.settings.session_max_age_seconds,
        httponly=True,
        secure=not container.settings.cookie_insecure_dev,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response
