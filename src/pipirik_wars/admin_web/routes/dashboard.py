"""Dashboard placeholder route (Sprint 4.5-A, §3.6)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    session = require_totp_verified(request)
    container = get_container(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        repo = SqlAlchemyAdminRepository(uow=uow)
        admin = await repo.get_by_tg_id(session.admin_id)

    templates = request.app.state.templates
    content: str = templates.get_template("dashboard.html").render(
        request=request,
        session=session,
        admin=admin,
    )
    return HTMLResponse(content=content)
