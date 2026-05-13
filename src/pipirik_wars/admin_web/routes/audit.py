"""Audit-log route (Sprint 4.5-F, ПД 4.5.7)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pipirik_wars.admin_web.deps import get_container, require_totp_verified
from pipirik_wars.application.admin.get_web_audit_log import (
    AuditLogFilters,
    GetWebAuditLog,
)
from pipirik_wars.infrastructure.db.services.admin_audit_web_query import (
    SqlAlchemyAdminAuditWebQuery,
)
from pipirik_wars.infrastructure.db.services.audit_query import (
    SqlAlchemyAuditLogQuery,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

router = APIRouter()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _parse_filters(request: Request) -> AuditLogFilters:
    params = request.query_params
    page_str = params.get("page", "1")
    try:
        page = int(page_str)
    except ValueError:
        page = 1

    return AuditLogFilters(
        date_from=_parse_datetime(params.get("date_from")),
        date_to=_parse_datetime(params.get("date_to")),
        actor_id=params.get("actor_id") or None,
        action=params.get("action") or None,
        source=params.get("source") or None,
        page=page,
        log_type=params.get("log_type", "all"),
    )


@router.get("/audit", response_class=HTMLResponse)
async def audit_log_page(request: Request) -> HTMLResponse:
    """Main audit log page with filters."""
    session = require_totp_verified(request)
    container = get_container(request)
    filters = _parse_filters(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        audit_query = SqlAlchemyAuditLogQuery(uow=uow)
        admin_audit_query = SqlAlchemyAdminAuditWebQuery(uow=uow)
        use_case = GetWebAuditLog(
            audit_query=audit_query,
            admin_audit_query=admin_audit_query,
        )
        result = await use_case.execute(filters)

    templates = request.app.state.templates
    content: str = templates.get_template("audit_log.html").render(
        request=request,
        session=session,
        result=result,
        filters=filters,
    )
    return HTMLResponse(content=content)


@router.get("/audit/table", response_class=HTMLResponse)
async def audit_log_table(request: Request) -> HTMLResponse:
    """HTMX partial: audit table rows only."""
    require_totp_verified(request)
    container = get_container(request)
    filters = _parse_filters(request)

    async with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        audit_query = SqlAlchemyAuditLogQuery(uow=uow)
        admin_audit_query = SqlAlchemyAdminAuditWebQuery(uow=uow)
        use_case = GetWebAuditLog(
            audit_query=audit_query,
            admin_audit_query=admin_audit_query,
        )
        result = await use_case.execute(filters)

    templates = request.app.state.templates
    content: str = templates.get_template("partials/audit_table.html").render(
        result=result,
        filters=filters,
    )
    return HTMLResponse(content=content)
