"""Use-case `FreezePlayer` (Спринт 2.5-B.3).

`/freeze <tg_id> [reason]` — обратимая заморозка игрока. Вызывается
админом-поддержкой, не требует TOTP (не разрушительная операция —
любой админ может тут же `/unfreeze`).

Контракт:
- актор должен быть `Admin.is_active`;
- target существует — иначе `PlayerNotFoundError`;
- идемпотентность на доменном уровне: повторная заморозка не меняет
  объект (см. `Player.freeze()` ГДД §1.5);
- audit-запись `ADMIN_PLAYER_FROZEN` пишется **только при реальной
  смене статуса** (если игрок и так был заморожен — лога нет, но
  use-case возвращает `was_already_frozen=True`, чтобы handler мог
  сказать «уже заморожен»);
- `before/after` фиксируем `status` (`active` → `frozen`).
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
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class FreezePlayerInput:
    actor_tg_id: int
    target_tg_id: int
    reason: str | None = None
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class FreezePlayerOutput:
    target_tg_id: int
    was_already_frozen: bool


class FreezePlayer:
    """Use-case ручной заморозки игрока."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: FreezePlayerInput) -> FreezePlayerOutput:
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
            command_kind=AdminCommandKind.FREEZE_PLAYER,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="player",
            target_id=str(inp.target_tg_id),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )
        async with self._uow:
            player = await self._players.get_by_tg_id(inp.target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=inp.target_tg_id)

            if player.status is PlayerStatus.FROZEN:
                # Идемпотентный no-op: ничего не пишем в БД, ничего не
                # пишем в audit (audit-лог отражает «состоявшуюся»
                # мутацию). Handler сообщит игроку «уже заморожен».
                return FreezePlayerOutput(
                    target_tg_id=inp.target_tg_id,
                    was_already_frozen=True,
                )

            frozen = player.freeze(now=now)
            await self._players.save(frozen)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
                    target_kind="player",
                    target_id=str(inp.target_tg_id),
                    before={"status": player.status.value},
                    after={"status": frozen.status.value},
                    reason=inp.reason or f"freeze:{inp.target_tg_id}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return FreezePlayerOutput(
            target_tg_id=inp.target_tg_id,
            was_already_frozen=False,
        )


__all__ = ["FreezePlayer", "FreezePlayerInput", "FreezePlayerOutput"]
