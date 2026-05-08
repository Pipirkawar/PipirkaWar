"""Use-case `CloseBossLobby` (Спринт 3.3-B, ГДД §10.3).

Триггерится APScheduler-job-ом, поставленным в `SummonBoss`
(в момент `lobby_ends_at`). В 3.3-D также может вызываться вручную
саммонером через `/boss_start` — поэтому контракт идемпотентен.

Контракт:

- если `status == LOBBY` — переводим `LOBBY → IN_BATTLE`, аудитим
  событие;
- если `status == IN_BATTLE | FINISHED | CANCELLED` — NO-OP
  (`was_already_closed=True`), не бросаем ошибку (был уже закрыт
  в параллельной транзакции или вручную).

В 3.3-C сюда же будет добавлено планирование первого `boss_round_tick`-job-а
и safety-net `boss_fight_finish`-job-а на момент конца боя; пока в 3.3-B
этот use-case ограничивается `LOBBY → IN_BATTLE`-переходом + audit-ом.
Use-case аккуратен в отношении гонки двух CloseBossLobby — `is_in_lobby`-
guard выполняется строго внутри `IUnitOfWork`, и при коммите второй
транзакции `mark_in_battle()` будет уже NO-OP.

ВАЖНО: длина рейдеров и саммонера на старте боя **не списывается**
— рейд-бой длинами торгует только на финише (3.3-C, `FinishBossFight`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CloseBossLobbyInput
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    IBossFightRepository,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class BossLobbyClosed:
    """Результат `CloseBossLobby`.

    `was_already_closed=True` — лобби было уже не `LOBBY` (no-op);
    транзакция ничего не меняла, аудит не писался.
    """

    boss_fight: BossFight
    was_already_closed: bool


class CloseBossLobby:
    """Use-case «закрыть лобби рейд-боя: LOBBY → IN_BATTLE» (ГДД §10.3)."""

    __slots__ = (
        "_audit",
        "_boss_fights",
        "_clock",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        boss_fights: IBossFightRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: CloseBossLobbyInput) -> BossLobbyClosed:
        """Закрыть лобби рейд-боя. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            boss_fight = await self._boss_fights.get_by_id(
                boss_fight_id=input_dto.boss_fight_id,
            )
            if boss_fight is None:
                raise BossFightNotFoundError(boss_fight_id=input_dto.boss_fight_id)
            assert boss_fight.id is not None

            if not boss_fight.is_in_lobby:
                # NO-OP — лобби уже закрыто в параллельной транзакции
                # или закрыто вручную / отменено. Возвращаем текущее
                # состояние, без аудита.
                return BossLobbyClosed(boss_fight=boss_fight, was_already_closed=True)

            transitioned = boss_fight.mark_in_battle()
            saved = await self._boss_fights.save(transitioned)
            assert saved.id is not None

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_FIGHT_STARTED,
                    actor_id=None,
                    target_kind="boss_fight",
                    target_id=str(saved.id),
                    before={"status": boss_fight.status.value},
                    after={"status": saved.status.value},
                    reason="boss_fight_started",
                    idempotency_key=f"boss_fight_started:{saved.id}",
                    occurred_at=now,
                )
            )

        return BossLobbyClosed(boss_fight=saved, was_already_closed=False)


__all__ = [
    "BossLobbyClosed",
    "CloseBossLobby",
]
