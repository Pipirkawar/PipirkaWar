"""Use-case `UnfreezePlayer` (Спринт 2.5-B.3).

`/unfreeze <tg_id>` — снятие ручной заморозки. Без TOTP. Идемпотентно
на доменном уровне: уже активный игрок — no-op.

Контракт зеркальный к `FreezePlayer`:
- актор должен быть `Admin.is_active`;
- target существует — иначе `PlayerNotFoundError`;
- audit-запись `ADMIN_PLAYER_UNFROZEN` пишется **только при реальной
  смене статуса** (если игрок и так активен — лога нет, а
  `was_already_active=True`);
- `before/after` фиксируем `status` (`frozen` → `active`).
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
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class UnfreezePlayerInput:
    actor_tg_id: int
    target_tg_id: int
    reason: str | None = None
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class UnfreezePlayerOutput:
    target_tg_id: int
    was_already_active: bool


class UnfreezePlayer:
    """Use-case ручной разморозки игрока."""

    __slots__ = ("_admins", "_audit", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: UnfreezePlayerInput) -> UnfreezePlayerOutput:
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
            player = await self._players.get_by_tg_id(inp.target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=inp.target_tg_id)

            if player.status is PlayerStatus.ACTIVE:
                return UnfreezePlayerOutput(
                    target_tg_id=inp.target_tg_id,
                    was_already_active=True,
                )

            unfrozen = player.unfreeze(now=now)
            await self._players.save(unfrozen)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PLAYER_UNFROZEN,
                    target_kind="player",
                    target_id=str(inp.target_tg_id),
                    before={"status": player.status.value},
                    after={"status": unfrozen.status.value},
                    reason=inp.reason or f"unfreeze:{inp.target_tg_id}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return UnfreezePlayerOutput(
            target_tg_id=inp.target_tg_id,
            was_already_active=False,
        )


__all__ = ["UnfreezePlayer", "UnfreezePlayerInput", "UnfreezePlayerOutput"]
