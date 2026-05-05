"""Use-case `EnqueueGlobalDuel` (Спринт 2.1.F.2, ГДД §7.1).

Постановка существующего `mode=GLOBAL_ONLY`-вызова в глобальную FIFO-
очередь. Вызывается из `ChallengeDuel` сразу после создания вызова
(если `mode=GLOBAL_ONLY`), а также после accept-а handler-ом
`/duel_global` для повторного попадания в очередь — этого пока нет в
текущем флоу, но порт допускает.

Алгоритм:

1. Загружает `Duel` по `duel_id`. Нет — `DuelNotFoundError`.
2. Проверка инвариантов: `mode == GLOBAL_ONLY` и `state ==
   PENDING_ACCEPT`. Иначе — `InvalidLobbyEnqueueError`.
3. `lobby.enqueue(duel_id=..., enqueued_at=now)` — идемпотентно.
   Если запись уже была (`False`), не дублируем audit, но всё равно
   планируем expiration (он `replace_existing=True`).
4. `scheduler.schedule_global_lobby_expiration(duel_id, run_at=now+ttl)`
   — снаружи UoW.
5. Audit `PVP_LOBBY_ENQUEUED` (только при первом enqueue).

Транзакция — ambient `IUnitOfWork`. Schedule вызывается **после**
коммита (snapshot-isolation для recovery: если процесс упадёт между
коммитом и scheduler.add_job, recovery-hook на старте перепланирует
job-ы по записи в `pvp_global_lobby`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import EnqueueGlobalDuelInput
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    IDuelRepository,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


class InvalidLobbyEnqueueError(Exception):
    """Дуэль не может быть поставлена в глобальную очередь.

    Причина — `mode != GLOBAL_ONLY` или `state != PENDING_ACCEPT`.
    """

    def __init__(self, *, duel_id: int, reason: str) -> None:
        self.duel_id = duel_id
        self.reason = reason
        super().__init__(
            f"Cannot enqueue duel_id={duel_id} into global lobby: {reason}",
        )


@dataclass(frozen=True, slots=True)
class GlobalDuelEnqueued:
    """Результат успешной постановки в очередь."""

    duel: Duel
    was_already_in_lobby: bool


class EnqueueGlobalDuel:
    """Use-case «поставить GLOBAL_ONLY-вызов в FIFO-очередь»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_duels",
        "_lobby",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        duels: IDuelRepository,
        lobby: IGlobalLobbyRepository,
        scheduler: IDelayedJobScheduler,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._duels = duels
        self._lobby = lobby
        self._scheduler = scheduler
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(
        self,
        input_dto: EnqueueGlobalDuelInput,
    ) -> GlobalDuelEnqueued:
        """Поставить вызов в глобальную очередь."""

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise DuelNotFoundError(duel_id=input_dto.duel_id)
            if duel.mode is not DuelMode.GLOBAL_ONLY:
                raise InvalidLobbyEnqueueError(
                    duel_id=input_dto.duel_id,
                    reason=f"mode={duel.mode.value} (expected global_only)",
                )
            if duel.state is not DuelState.PENDING_ACCEPT:
                raise InvalidLobbyEnqueueError(
                    duel_id=input_dto.duel_id,
                    reason=f"state={duel.state.value} (expected pending_accept)",
                )

            assert duel.id is not None
            now = self._clock.now()
            cfg = self._balance.get().pvp.duel_1v1
            enqueued_now = await self._lobby.enqueue(
                duel_id=duel.id,
                enqueued_at=now,
            )
            run_at = now + timedelta(minutes=cfg.global_lobby_ttl_minutes)

            if enqueued_now:
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.PVP_LOBBY_ENQUEUED,
                        actor_id=None,
                        target_kind="pvp_duel",
                        target_id=str(duel.id),
                        before=None,
                        after={"enqueued_at": now.isoformat()},
                        reason="pvp_lobby_enqueued",
                        idempotency_key=f"pvp_lobby_enqueued:{duel.id}",
                        occurred_at=now,
                    )
                )

            duel_id_for_schedule = duel.id

        await self._scheduler.schedule_global_lobby_expiration(
            duel_id=duel_id_for_schedule,
            run_at=run_at,
        )
        return GlobalDuelEnqueued(
            duel=duel,
            was_already_in_lobby=not enqueued_now,
        )


__all__ = [
    "EnqueueGlobalDuel",
    "GlobalDuelEnqueued",
    "InvalidLobbyEnqueueError",
]
