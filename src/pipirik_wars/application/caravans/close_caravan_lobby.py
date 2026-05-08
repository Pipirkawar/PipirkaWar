"""Use-case `CloseCaravanLobby` (Спринт 3.2-B, расширен в 3.2-C, ГДД §9.3).

Триггерится APScheduler-job-ом, поставленным в `CreateCaravan`
(в момент `now + caravans.lobby_minutes`), либо может быть вызван
вручную из 3.2-D handler-ом «Командир каравана нажал /caravan_start».

Контракт идемпотентен:

- если `status == LOBBY` — переводим `LOBBY → IN_BATTLE`, аудитим
  событие, шедулим `caravan_battle_finish`-job на `caravan.battle_ends_at`;
- если `status == IN_BATTLE | FINISHED | CANCELLED` — NO-OP, не
  бросаем ошибку (был уже закрыт в параллельной транзакции или
  закрыт вручную по `/caravan_start`).

3.2-C добавил планирование `caravan_battle_finish`-job-а внутри этой
же транзакции: после успешного `mark_in_battle()` зовём
`IDelayedJobScheduler.schedule_caravan_battle_finish(...)`.
Соответствующий callback в APScheduler-е (`_run_caravan_battle_finish_job`)
вызывает `FinishCaravanBattle` use-case. Сам resolve-боя — в нём.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CloseCaravanLobbyInput
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanNotFoundError,
    ICaravanRepository,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class ClosedCaravanLobby:
    """Результат `CloseCaravanLobby`.

    `was_already_closed=True` — лобби было уже не `LOBBY` (no-op);
    транзакция ничего не меняла, аудит не писался.
    """

    caravan: Caravan
    was_already_closed: bool


class CloseCaravanLobby:
    """Use-case «закрыть лобби: LOBBY → IN_BATTLE» (ГДД §9.3)."""

    __slots__ = (
        "_audit",
        "_caravans",
        "_clock",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        caravans: ICaravanRepository,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: CloseCaravanLobbyInput) -> ClosedCaravanLobby:
        """Закрыть лобби. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            caravan = await self._caravans.get_by_id(caravan_id=input_dto.caravan_id)
            if caravan is None:
                raise CaravanNotFoundError(caravan_id=input_dto.caravan_id)
            assert caravan.id is not None

            if not caravan.is_in_lobby:
                # NO-OP — лобби уже закрыто в параллельной транзакции
                # или закрыто вручную. Возвращаем текущее состояние,
                # без аудита.
                return ClosedCaravanLobby(caravan=caravan, was_already_closed=True)

            transitioned = caravan.mark_in_battle()
            saved = await self._caravans.save(transitioned)
            assert saved.id is not None

            # 3.2-C: шедулим финиш-боя на `battle_ends_at`. APScheduler
            # `replace_existing=True`, поэтому повторный вызов на гонке
            # двух CloseCaravanLobby (что блокирует idempotency-чек выше)
            # безопасен.
            await self._scheduler.schedule_caravan_battle_finish(
                caravan_id=saved.id,
                run_at=saved.battle_ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_LOBBY_CLOSED,
                    actor_id=None,
                    target_kind="caravan",
                    target_id=str(saved.id),
                    before={"status": caravan.status.value},
                    after={"status": saved.status.value},
                    reason="caravan_lobby_closed",
                    idempotency_key=f"caravan_lobby_closed:{saved.id}",
                    occurred_at=now,
                )
            )

        return ClosedCaravanLobby(caravan=saved, was_already_closed=False)


__all__ = [
    "CloseCaravanLobby",
    "ClosedCaravanLobby",
]
