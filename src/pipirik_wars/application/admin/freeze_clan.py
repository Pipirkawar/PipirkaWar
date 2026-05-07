"""Use-case `FreezeClanAdmin` (Спринт 2.5-D.2).

`/freeze_clan <id|chat_id> [reason]` — ручная заморозка клана админом.
Не требует TOTP (обратимая операция; админ может тут же
`/unfreeze_clan`). Отличается от автоматической `FreezeClan`
(`application/clan/freeze.py`, реакция на `bot kicked`):

* привязана к актору-админу (пишется в `admin_audit_log`, action =
  `ADMIN_CLAN_FROZEN`);
* идентифицирует клан по `Clan.id` или Telegram `chat_id` (двойной
  lookup по аналогии с `/clan`);
* идемпотентна на доменном уровне: повторная заморозка возвращает
  `was_already_frozen=True`, без аудит-записи.

Семантика:

- актор должен быть `Admin.is_active` — иначе `AuthorizationError`;
- если клан не найден ни по `id`, ни по `chat_id` → возвращаем
  `outcome="not_found"` (handler покажет friendly «клан не найден»);
- если уже заморожен → `outcome="already_frozen"`, без аудит-записи;
- иначе `outcome="frozen"`, audit-запись `ADMIN_CLAN_FROZEN` с
  `before={"status": "active"}`, `after={"status": "frozen"}`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.clan import Clan, ClanStatus, IClanRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class FreezeClanAdminInput:
    """Параметры команды `/freeze_clan`.

    `query` — целое число (внутренний id или Telegram chat_id).
    """

    actor_tg_id: int
    query: int
    reason: str | None = None
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class FreezeClanAdminOutput:
    """`outcome`:

    * `"frozen"` — клан только что заморожен.
    * `"already_frozen"` — был уже frozen, ничего не делали.
    * `"not_found"` — клана с таким id/chat_id нет.
    """

    query: int
    outcome: str
    clan: Clan | None


class FreezeClanAdmin:
    """Use-case ручной заморозки клана админом."""

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

    async def execute(self, inp: FreezeClanAdminInput) -> FreezeClanAdminOutput:
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
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.FREEZE_CLAN,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="clan",
            target_id=str(inp.query),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )
        async with self._uow:
            clan = await self._clans.get_by_id(inp.query)
            if clan is None:
                clan = await self._clans.get_by_chat_id(inp.query)
            if clan is None:
                return FreezeClanAdminOutput(
                    query=inp.query,
                    outcome="not_found",
                    clan=None,
                )
            if clan.is_frozen:
                return FreezeClanAdminOutput(
                    query=inp.query,
                    outcome="already_frozen",
                    clan=clan,
                )
            if clan.id is None:  # pragma: no cover — invariant
                raise IntegrityError("clan loaded without id")

            frozen = clan.freeze(now=now)
            saved = await self._clans.save(frozen)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CLAN_FROZEN,
                    target_kind="clan",
                    target_id=str(saved.id),
                    before={"status": ClanStatus.ACTIVE.value},
                    after={"status": ClanStatus.FROZEN.value},
                    reason=inp.reason or f"freeze_clan:{saved.id}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return FreezeClanAdminOutput(query=inp.query, outcome="frozen", clan=saved)


__all__ = ["FreezeClanAdmin", "FreezeClanAdminInput", "FreezeClanAdminOutput"]
