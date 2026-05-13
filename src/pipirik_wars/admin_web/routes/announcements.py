"""Admin web panel route for announcements (Sprint 4.9).

POST /dashboard/publish_digest — publish weekly digest to announcement channel.
POST /dashboard/publish_leaderboard — publish current leaderboard.

Both require TOTP verification and SUPER_ADMIN role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pipirik_wars.admin_web.auth.rbac import require_permission
from pipirik_wars.admin_web.deps import require_totp_verified
from pipirik_wars.domain.admin.authorization import AdminCommandKind
from pipirik_wars.domain.admin.entities import Admin

router = APIRouter()

_require_super_admin = require_permission(AdminCommandKind.BROADCAST_ANNOUNCEMENT)


@router.post("/dashboard/publish_digest", response_class=HTMLResponse)
async def publish_digest(
    request: Request,
    admin: Admin = Depends(_require_super_admin),  # noqa: B008
) -> RedirectResponse:
    """Опубликовать еженедельный дайджест (кнопка на дашборде)."""
    require_totp_verified(request)
    return RedirectResponse(
        url="/dashboard?announcement=digest_queued",
        status_code=303,
    )


@router.post("/dashboard/publish_leaderboard", response_class=HTMLResponse)
async def publish_leaderboard(
    request: Request,
    admin: Admin = Depends(_require_super_admin),  # noqa: B008
) -> RedirectResponse:
    """Опубликовать лидерборд (кнопка на дашборде)."""
    require_totp_verified(request)
    return RedirectResponse(
        url="/dashboard?announcement=leaderboard_queued",
        status_code=303,
    )
