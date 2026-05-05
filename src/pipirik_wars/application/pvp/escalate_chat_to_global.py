"""Use-case `EscalateChatToGlobal` (Спринт 2.1.F.2, ГДД §7.1).

Job-эскалации: через `pvp.duel_1v1.chat_to_global_promotion_minutes`
после создания `mode=CHAT_THEN_GLOBAL`-вызова шедулер дёргает этот
use-case. Если дуэль ещё `PENDING_ACCEPT` — переводим её в
`GLOBAL_ONLY`, ставим в глобальное FIFO-лобби и планируем job
истечения TTL. Если уже принята/отменена — NO-OP.

Алгоритм:

1. Загружаем `Duel` по `duel_id`. Нет — NO-OP (уже удалена).
2. Если `state != PENDING_ACCEPT` — NO-OP (приняли или отменили
   быстрее, чем сработал job).
3. Если `mode != CHAT_THEN_GLOBAL` — NO-OP (например, был перевызван
   handler-ом). На такой случай не падаем — это benign-исход.
4. `Duel.escalate_to_global(now=...)` → `IDuelRepository.save(...)`.
5. `lobby_repo.enqueue(duel_id=..., enqueued_at=now)`.
6. `scheduler.schedule_global_lobby_expiration(duel_id, run_at=now + ttl)`.
7. Audit `PVP_LOBBY_ESCALATED`.

Транзакция — ambient `IUnitOfWork`. Schedule expiration делается
**после** успешного коммита БД (для этого вызывается **снаружи** UoW).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import EscalateChatToGlobalInput
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
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


@dataclass(frozen=True, slots=True)
class DuelEscalated:
    """Результат успешной эскалации chat→global."""

    duel: Duel


@dataclass(frozen=True, slots=True)
class DuelEscalationSkipped:
    """Эскалация — NO-OP (дуэль уже принята/отменена/не найдена)."""

    reason: str


class EscalateChatToGlobal:
    """Use-case «авто-эскалация CHAT_THEN_GLOBAL → GLOBAL_ONLY»."""

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
        input_dto: EscalateChatToGlobalInput,
    ) -> DuelEscalated | DuelEscalationSkipped:
        """Эскалировать вызов в глобальное лобби."""

        run_at_for_expiration = None
        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                return DuelEscalationSkipped(reason="not_found")
            if duel.state is not DuelState.PENDING_ACCEPT:
                return DuelEscalationSkipped(reason="not_pending_accept")
            if duel.mode is not DuelMode.CHAT_THEN_GLOBAL:
                return DuelEscalationSkipped(reason="not_chat_then_global")

            cfg = self._balance.get().pvp.duel_1v1
            now = self._clock.now()
            escalated = duel.escalate_to_global(now=now)
            saved = await self._duels.save(escalated)

            assert saved.id is not None
            await self._lobby.enqueue(duel_id=saved.id, enqueued_at=now)

            run_at_for_expiration = now + timedelta(
                minutes=cfg.global_lobby_ttl_minutes,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_LOBBY_ESCALATED,
                    actor_id=None,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before={"mode": duel.mode.value},
                    after={"mode": saved.mode.value},
                    reason="pvp_lobby_escalated",
                    idempotency_key=f"pvp_lobby_escalated:{saved.id}",
                    occurred_at=now,
                )
            )

            duel_id_for_schedule = saved.id

        # вне UoW — schedule вызывается только если транзакция успешно закоммитилась
        await self._scheduler.schedule_global_lobby_expiration(
            duel_id=duel_id_for_schedule,
            run_at=run_at_for_expiration,
        )
        return DuelEscalated(duel=saved)


__all__ = [
    "DuelEscalated",
    "DuelEscalationSkipped",
    "EscalateChatToGlobal",
]
