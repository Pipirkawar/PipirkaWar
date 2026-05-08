"""Use-case `CloseCaravanLobby` (Спринт 3.2-B, ГДД §9.3).

Триггерится APScheduler-job-ом, поставленным в `CreateCaravan`
(в момент `now + caravans.lobby_minutes`), либо может быть вызван
вручную из 3.2-D handler-ом «Командир каравана нажал /caravan_start».

Контракт идемпотентен:

- если `status == LOBBY` — переводим `LOBBY → IN_BATTLE`, аудитим
  событие;
- если `status == IN_BATTLE | FINISHED | CANCELLED` — NO-OP, не
  бросаем ошибку (был уже закрыт в параллельной транзакции или
  закрыт вручную lhassл по `/caravan_start`).

3.2-B **не** реализует resolve-боя — это Спринт 3.2-C. Здесь только
state-transition + audit. Финальный таймер (`battle_ends_at`)
планирует выходящий слой DI (3.2-C добавит `schedule_caravan_battle_finish`
сюда же или соседним хендлером).
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
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        caravans: ICaravanRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._audit = audit
        self._clock = clock

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
