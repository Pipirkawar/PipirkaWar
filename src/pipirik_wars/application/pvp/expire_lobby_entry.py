"""Use-case `ExpireLobbyEntry` (Спринт 2.1.F.2, ГДД §7.1).

Job-истечения TTL глобального лобби: через
`pvp.duel_1v1.global_lobby_ttl_minutes` после попадания дуэли в лобби
шедулер дёргает этот use-case. Если дуэль ещё в лобби (никто не принял
вовремя) — отменяем её, освобождаем activity-lock челленджера и пишем
audit `PVP_LOBBY_EXPIRED` + `PVP_DUEL_CANCELLED`. Если уже не в лобби
(приняли через `MatchFromLobby` или отменил сам челленджер) — NO-OP.

Алгоритм:

1. `lobby.is_in_lobby(duel_id)` — если `False`, NO-OP (убрали раньше).
2. Загружаем `Duel`. Нет — NO-OP.
3. Если `state != PENDING_ACCEPT` — NO-OP (race с accept).
4. `Duel.cancel(now=...)` → `IDuelRepository.save(...)`.
5. `lobby.remove(duel_id=...)`.
6. `locks.release(actor_kind="player", actor_id=challenger_id)`.
7. Audit `PVP_LOBBY_EXPIRED` + `PVP_DUEL_CANCELLED`.

Транзакция — ambient `IUnitOfWork`. Все три мутации (Duel.save +
lobby.remove + audit) — атомарны.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import ExpireLobbyEntryInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import (
    Duel,
    DuelState,
    IDuelRepository,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class LobbyEntryExpired:
    """Результат успешного истечения TTL."""

    duel: Duel


@dataclass(frozen=True, slots=True)
class LobbyEntryExpirationSkipped:
    """Истечение — NO-OP (дуэль не в лобби или уже завершена)."""

    reason: str


class ExpireLobbyEntry:
    """Use-case «истёк TTL глобального лобби — отменяем дуэль»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_duels",
        "_lobby",
        "_locks",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        duels: IDuelRepository,
        lobby: IGlobalLobbyRepository,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._duels = duels
        self._lobby = lobby
        self._locks = locks
        self._audit = audit
        self._clock = clock

    async def execute(
        self,
        input_dto: ExpireLobbyEntryInput,
    ) -> LobbyEntryExpired | LobbyEntryExpirationSkipped:
        """Истечь TTL и отменить дуэль (или NO-OP)."""

        async with self._uow:
            in_lobby = await self._lobby.is_in_lobby(duel_id=input_dto.duel_id)
            if not in_lobby:
                return LobbyEntryExpirationSkipped(reason="not_in_lobby")

            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                return LobbyEntryExpirationSkipped(reason="not_found")
            if duel.state is not DuelState.PENDING_ACCEPT:
                # race с accept-ом: дуэль приняли, expiration job-у не успели снять
                await self._lobby.remove(duel_id=input_dto.duel_id)
                return LobbyEntryExpirationSkipped(reason="not_pending_accept")

            now = self._clock.now()
            cancelled = duel.cancel(now=now)
            saved = await self._duels.save(cancelled)
            await self._lobby.remove(duel_id=input_dto.duel_id)

            await self._locks.release(
                actor_kind="player",
                actor_id=duel.challenger_id,
            )

            assert saved.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_LOBBY_EXPIRED,
                    actor_id=None,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before={"state": duel.state.value},
                    after={"state": saved.state.value},
                    reason="pvp_lobby_ttl_expired",
                    idempotency_key=f"pvp_lobby_expired:{saved.id}",
                    occurred_at=now,
                )
            )
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_DUEL_CANCELLED,
                    actor_id=None,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before={"state": duel.state.value},
                    after={"state": saved.state.value},
                    reason="pvp_duel_cancelled_by_lobby_expiration",
                    idempotency_key=f"pvp_duel_cancelled:{saved.id}",
                    occurred_at=now,
                )
            )
        return LobbyEntryExpired(duel=saved)


__all__ = [
    "ExpireLobbyEntry",
    "LobbyEntryExpirationSkipped",
    "LobbyEntryExpired",
]
