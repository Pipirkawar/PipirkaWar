"""TOTP setup & verification routes (Sprint 4.5-A, §3.3–3.5)."""

from __future__ import annotations

import base64
import hmac as _hmac
import io
import logging
import time

import qrcode
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pipirik_wars.admin_web.deps import get_container, require_session
from pipirik_wars.application.admin.setup_totp import build_provisioning_uri
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


@router.get("/totp", response_class=HTMLResponse)
async def totp_page(request: Request) -> HTMLResponse | RedirectResponse:
    session = require_session(request)
    container = get_container(request)

    if session.totp_verified_at is not None:
        ttl = container.settings.totp_verify_ttl_seconds
        if time.time() - session.totp_verified_at <= ttl:
            return RedirectResponse(url="/dashboard", status_code=302)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)

    templates = request.app.state.templates

    if admin is None or admin.totp_secret is None:
        content: str = templates.get_template("totp_setup.html").render(
            request=request,
            session=session,
            bootstrap_not_configured=container.bootstrap_admin_password is None,
        )
        return HTMLResponse(content=content)

    content = templates.get_template("totp_verify.html").render(
        request=request,
        session=session,
    )
    return HTMLResponse(content=content)


@router.post("/totp/setup")
async def totp_setup(request: Request) -> HTMLResponse | RedirectResponse:
    session = require_session(request)
    container = get_container(request)

    form = getattr(request.state, "form_cache", None) or await request.form()
    bootstrap_password = str(form.get("bootstrap_password", ""))

    templates = request.app.state.templates

    if container.bootstrap_admin_password is None:
        content: str = templates.get_template("totp_setup.html").render(
            request=request,
            session=session,
            error="Bootstrap password is not configured. Contact super-admin via bot.",
            bootstrap_not_configured=True,
        )
        return HTMLResponse(content=content)

    if not _hmac.compare_digest(container.bootstrap_admin_password, bootstrap_password):
        content = templates.get_template("totp_setup.html").render(
            request=request,
            session=session,
            error="Invalid bootstrap password",
            bootstrap_not_configured=False,
        )
        return HTMLResponse(content=content)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)

        if admin is None or not admin.is_active:
            return RedirectResponse(url="/", status_code=302)

        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            return RedirectResponse(url="/", status_code=302)

        if admin.totp_secret is not None:
            return RedirectResponse(url="/totp", status_code=302)

        new_secret = container.totp_secret_generator.generate()
        await repo.set_totp_secret(admin_id=admin_id, secret=new_secret)

        audit = SqlAlchemyAdminAuditLogger(uow=uow)
        await audit.record(
            AdminAuditEntry(
                admin_id=admin_id,
                action=AdminAuditAction.ADMIN_TOTP_SETUP,
                target_kind="admin",
                target_id=str(admin_id),
                before=None,
                after=None,
                reason="TOTP setup via admin web panel",
                idempotency_key=None,
                source=AdminAuditSource.WEB,
                tg_chat_id=None,
                ip=request.client.host if request.client else None,
                occurred_at=container.clock.now(),
            ),
        )
        await uow.commit()

    prov_uri = build_provisioning_uri(
        secret=new_secret,
        account_name=f"admin_{admin_id}",
    )

    qr_img = qrcode.make(prov_uri)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    content = templates.get_template("totp_setup.html").render(
        request=request,
        session=session,
        qr_data_uri=f"data:image/png;base64,{qr_b64}",
        secret=new_secret,
        bootstrap_not_configured=False,
        setup_complete=True,
    )
    return HTMLResponse(content=content)


@router.post("/totp/verify")
async def totp_verify(request: Request) -> HTMLResponse | RedirectResponse:
    session = require_session(request)
    container = get_container(request)

    form = getattr(request.state, "form_cache", None) or await request.form()
    code = str(form.get("code", "")).strip()

    templates = request.app.state.templates

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)

        if admin is None or not admin.is_active or admin.totp_secret is None:
            return RedirectResponse(url="/", status_code=302)

        if container.totp_verifier.verify(secret=admin.totp_secret, code=code):
            session.totp_verified_at = time.time()
            cookie_value = container.session_manager.encode(session)
            response = RedirectResponse(url="/dashboard", status_code=302)
            response.set_cookie(
                key="session",
                value=cookie_value,
                max_age=container.settings.session_max_age_seconds,
                httponly=True,
                secure=not container.settings.cookie_insecure_dev,
                samesite="lax",
            )
            return response

    content: str = templates.get_template("totp_verify.html").render(
        request=request,
        session=session,
        error="Invalid code. Please try again.",
    )
    return HTMLResponse(content=content)
