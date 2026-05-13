"""Dashboard route with RBAC (Sprint 4.5-A scaffold, Sprint 4.5-B RBAC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from pipirik_wars.admin_web.auth.rbac import require_permission
from pipirik_wars.admin_web.deps import require_totp_verified
from pipirik_wars.domain.admin.authorization import AdminCommandKind
from pipirik_wars.domain.admin.entities import Admin

router = APIRouter()

_require_admin_stats = require_permission(AdminCommandKind.ADMIN_STATS)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin: Admin = Depends(_require_admin_stats),  # noqa: B008
) -> HTMLResponse:
    session = require_totp_verified(request)

    templates = request.app.state.templates
    content: str = templates.get_template("dashboard.html").render(
        request=request,
        session=session,
        admin=admin,
    )
    return HTMLResponse(content=content)
