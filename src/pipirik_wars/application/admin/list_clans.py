"""Use-case `ListClansAdmin` (Sprint 4.5-E, task 4.5.6).

Paginated clan list for the admin web panel ``/clans`` section.
Supports optional status filter (all / frozen).

Read-only — TOTP not required.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.clan import Clan, ClanStatus, IClanRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ListClansAdminInput:
    actor_tg_id: int
    status_filter: ClanStatus | None = None
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class ListClansAdminOutput:
    clans: Sequence[Clan]
    total: int
    page: int
    page_size: int
    status_filter: ClanStatus | None


class ListClansAdmin:
    """Use-case: paginated clan list with optional status filter."""

    __slots__ = ("_admins", "_audit", "_authz", "_clans", "_clock", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        clans: IClanRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._clans = clans
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: ListClansAdminInput) -> ListClansAdminOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.LIST_CLANS,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="clan",
            target_id="list",
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        page = max(1, inp.page)
        page_size = max(1, min(MAX_PAGE_SIZE, inp.page_size))
        offset = (page - 1) * page_size

        async with self._uow:
            clans = await self._clans.list_all(
                status_filter=inp.status_filter,
                limit=page_size,
                offset=offset,
            )
            total = await self._clans.count_all(status_filter=inp.status_filter)

        return ListClansAdminOutput(
            clans=clans,
            total=total,
            page=page,
            page_size=page_size,
            status_filter=inp.status_filter,
        )


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ListClansAdmin",
    "ListClansAdminInput",
    "ListClansAdminOutput",
]
