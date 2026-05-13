"""Use-case ``GetWebAuditLog`` (Sprint 4.5-F, ПД 4.5.7).

Unified audit-log query for the web admin panel. Merges records from
both ``audit_log`` (bot/game events) and ``admin_audit_log`` (admin
actions) into a single chronologically-sorted page. Supports filtering
by date range, actor (player tg_id or admin tg_id), action type, and
source (``bot`` / ``web``). Offset-based pagination.

The use-case does NOT write to ``admin_audit_log`` (unlike the bot's
``/audit`` command) — the web panel is read-only for observability.
Authorization is enforced at the route level via ``require_totp_verified``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.domain.admin import (
    AdminAuditRecord,
    IAdminAuditWebQuery,
)
from pipirik_wars.domain.shared.ports.audit import AuditRecord, IAuditLogQuery

PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class AuditLogFilters:
    """Filters for the audit log query."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    actor_id: str | None = None
    action: str | None = None
    source: str | None = None
    page: int = 1
    log_type: str = "all"


@dataclass(frozen=True, slots=True)
class AuditLogPage:
    """Paginated result for audit log display."""

    audit_records: Sequence[AuditRecord]
    admin_audit_records: Sequence[AdminAuditRecord]
    total_audit: int
    total_admin_audit: int
    filters: AuditLogFilters
    page_size: int


class GetWebAuditLog:
    """Read-side use-case for the web audit-log section."""

    __slots__ = ("_admin_audit_query", "_audit_query")

    def __init__(
        self,
        *,
        audit_query: IAuditLogQuery,
        admin_audit_query: IAdminAuditWebQuery,
    ) -> None:
        self._audit_query = audit_query
        self._admin_audit_query = admin_audit_query

    async def execute(self, filters: AuditLogFilters) -> AuditLogPage:
        page = max(1, filters.page)
        limit = PAGE_SIZE
        offset = (page - 1) * limit

        actor_id_int: int | None = None
        if filters.actor_id:
            try:
                actor_id_int = int(filters.actor_id)
            except ValueError:
                actor_id_int = None

        audit_records: Sequence[AuditRecord] = ()
        admin_audit_records: Sequence[AdminAuditRecord] = ()
        total_audit = 0
        total_admin_audit = 0

        common_kw = {
            "date_from": filters.date_from,
            "date_to": filters.date_to,
            "action": filters.action,
            "source": filters.source,
        }

        if filters.log_type in ("all", "bot"):
            audit_records = await self._audit_query.list_records(
                limit=limit,
                offset=offset,
                actor_id=actor_id_int,
                **common_kw,  # type: ignore[arg-type]
            )
            total_audit = await self._audit_query.count(
                actor_id=actor_id_int,
                **common_kw,  # type: ignore[arg-type]
            )

        if filters.log_type in ("all", "admin"):
            admin_audit_records = await self._admin_audit_query.list_records(
                limit=limit,
                offset=offset,
                admin_id=actor_id_int,
                **common_kw,  # type: ignore[arg-type]
            )
            total_admin_audit = await self._admin_audit_query.count(
                admin_id=actor_id_int,
                **common_kw,  # type: ignore[arg-type]
            )

        return AuditLogPage(
            audit_records=audit_records,
            admin_audit_records=admin_audit_records,
            total_audit=total_audit,
            total_admin_audit=total_admin_audit,
            filters=filters,
            page_size=limit,
        )
