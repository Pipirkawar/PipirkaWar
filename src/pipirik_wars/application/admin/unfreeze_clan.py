"""Use-case `UnfreezeClanAdmin` (Спринт 2.5-D.2).

`/unfreeze_clan <id|chat_id>` — ручная разморозка клана админом
(зеркало `FreezeClanAdmin`).

Семантика:

- актор должен быть `Admin.is_active`;
- если клан не найден → `outcome="not_found"`;
- если уже active → `outcome="already_active"`, без аудит-записи;
- иначе `outcome="unfrozen"`, audit-запись `ADMIN_CLAN_UNFROZEN`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminRepository,
)
from pipirik_wars.domain.clan import Clan, ClanStatus, IClanRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class UnfreezeClanAdminInput:
    actor_tg_id: int
    query: int
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class UnfreezeClanAdminOutput:
    """`outcome`:

    * `"unfrozen"` — клан только что разморожен.
    * `"already_active"` — был уже active.
    * `"not_found"` — клана с таким id/chat_id нет.
    """

    query: int
    outcome: str
    clan: Clan | None


class UnfreezeClanAdmin:
    """Use-case ручной разморозки клана админом."""

    __slots__ = ("_admins", "_audit", "_clans", "_clock", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        clans: IClanRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._clans = clans
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: UnfreezeClanAdminInput) -> UnfreezeClanAdminOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        now = self._clock.now()
        async with self._uow:
            clan = await self._clans.get_by_id(inp.query)
            if clan is None:
                clan = await self._clans.get_by_chat_id(inp.query)
            if clan is None:
                return UnfreezeClanAdminOutput(
                    query=inp.query,
                    outcome="not_found",
                    clan=None,
                )
            if clan.status is ClanStatus.ACTIVE:
                return UnfreezeClanAdminOutput(
                    query=inp.query,
                    outcome="already_active",
                    clan=clan,
                )
            if clan.id is None:  # pragma: no cover — invariant
                raise IntegrityError("clan loaded without id")

            unfrozen = clan.unfreeze(now=now)
            saved = await self._clans.save(unfrozen)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CLAN_UNFROZEN,
                    target_kind="clan",
                    target_id=str(saved.id),
                    before={"status": ClanStatus.FROZEN.value},
                    after={"status": ClanStatus.ACTIVE.value},
                    reason=f"unfreeze_clan:{saved.id}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return UnfreezeClanAdminOutput(query=inp.query, outcome="unfrozen", clan=saved)


__all__ = [
    "UnfreezeClanAdmin",
    "UnfreezeClanAdminInput",
    "UnfreezeClanAdminOutput",
]
