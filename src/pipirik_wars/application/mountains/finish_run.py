"""Use-case `FinishMountainRun` (Спринт 3.1-B).

Срабатывает по APScheduler-job-у, запланированному `StartMountainRun`-ом
на `ends_at`. Применяет уже сохранённый исход:

1. Находит `mountain_runs` по `run_id`. Нет — `MountainRunNotFoundError`.
2. Если запись уже `FINISHED` — идемпотентный no-op (job мог стрельнуть
   повторно из-за рестарта воркера или ручного `cancel`/`reschedule`).
3. Загружает `Player` по `mountain_runs.player_id`.
4. Применяет дельту длины:
   - **gain** (`length_delta_cm > 0`) — через `ILengthGranter.grant(
     source=AuditSource.MOUNTAINS, ...)`. `AddLength` сам пишет audit
     `LENGTH_GRANT`, клампит по anti-cheat cap-ам, взводит trip-wire.
   - **loss** (`length_delta_cm < 0`) — прямой `Player.with_length(
     max(0, length + delta))` + audit `LENGTH_REVOKE`. Cap-ы прибавки
     (Спринт 1.6) к вычитаниям неприменимы — это та же модель, что в
     `application/pvp/apply_outcome.py`.
   - `0` — не трогаем длину и не пишем audit.
5. Помечает `mountain_runs.status = FINISHED, finished_at = now`.
6. Снимает `activity_lock` `(player, MOUNTAINS)` (NO-OP, если истёк).
7. Пишет `audit_log(action=MOUNTAIN_RUN_FINISHED)` с
   `idempotency_key=f"mountain_run_finished:{run.id}"`.
8. Дроп предметов в инвентарь — НЕ применяется здесь (это handler-задача
   3.1-E: пользователь жмёт «надеть/выбросить»). Use-case только сохраняет
   список дропов в `mountain_runs.drops` и возвращает их handler-у.

Транзакция: всё внутри одного `IUnitOfWork`. `ILengthGranter.grant(...)`
вызывается в ambient-режиме внутри этого контекста.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import FinishMountainRunInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.mountains import (
    IMountainRunRepository,
    MountainRun,
    MountainRunNotFoundError,
    MountainRunStatus,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.player.value_objects import Length
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class MountainRunFinished:
    """Результат финиша. Используется bot-handler-ом (Спринт 3.1-E)
    для формирования сообщения «вернулся из гор» (ГДД §8.2).

    Поля:
    - `run` — финальная запись `mountain_runs` (`status=FINISHED`).
    - `player_before` / `player_after` — снимки игрока до/после применения
      исхода.
    - `was_already_finished` — `True`, если повторный вызов на уже
      финишированном забеге (handler не отправляет сообщение второй раз).
    """

    run: MountainRun
    player_before: Player
    player_after: Player
    was_already_finished: bool


class FinishMountainRun:
    """Use-case «применить результат похода в горы и снять блок»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_length_granter",
        "_locks",
        "_players",
        "_runs",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        runs: IMountainRunRepository,
        locks: ActivityLockService,
        length_granter: ILengthGranter,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._runs = runs
        self._locks = locks
        self._length_granter = length_granter
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: FinishMountainRunInput) -> MountainRunFinished:
        """Финишировать поход в горы. См. docstring модуля для контракта."""
        async with self._uow:
            run = await self._runs.get_by_id(run_id=input_dto.run_id)
            if run is None:
                raise MountainRunNotFoundError(run_id=input_dto.run_id)

            player = await self._players.get_by_id(player_id=run.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=run.player_id)

            if run.status is MountainRunStatus.FINISHED:
                return MountainRunFinished(
                    run=run,
                    player_before=player,
                    player_after=player,
                    was_already_finished=True,
                )

            now = self._clock.now()
            player_before = player
            assert player.id is not None
            assert run.id is not None

            if run.length_delta_cm > 0:
                await self._length_granter.grant(
                    player_id=player.id,
                    delta_cm=run.length_delta_cm,
                    source=AuditSource.MOUNTAINS,
                    reason="mountain_run_finished",
                    idempotency_key=f"add_length:mountain_run:{run.id}",
                )
            elif run.length_delta_cm < 0:
                new_cm = max(0, player.length.cm + run.length_delta_cm)
                new_length = Length(cm=new_cm)
                after = player.with_length(new_length, now=now)
                saved_player_after_loss = await self._players.save(after)
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.LENGTH_REVOKE,
                        actor_id=player.tg_id,
                        target_kind="player",
                        target_id=str(player.id),
                        before={"length_cm": player.length.cm},
                        after={"length_cm": saved_player_after_loss.length.cm},
                        reason="mountain_run_loss",
                        idempotency_key=f"mountain_run_loss_revoke:{run.id}",
                        occurred_at=now,
                        source=AuditSource.MOUNTAINS,
                        delta_cm=run.length_delta_cm,
                    )
                )

            saved_player = await self._players.get_by_id(player_id=player.id) or player
            finished_run = await self._runs.save(run.mark_finished(finished_at=now))

            await self._locks.release(actor_kind="player", actor_id=run.player_id)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.MOUNTAIN_RUN_FINISHED,
                    actor_id=player.tg_id,
                    target_kind="mountain_run",
                    target_id=str(finished_run.id),
                    before={"status": MountainRunStatus.IN_PROGRESS.value},
                    after={
                        "status": MountainRunStatus.FINISHED.value,
                        "branch_name": finished_run.branch_name,
                        "length_delta_cm": finished_run.length_delta_cm,
                        "drops_count": len(finished_run.drops),
                        "finished_at": (
                            finished_run.finished_at.isoformat()
                            if finished_run.finished_at is not None
                            else None
                        ),
                    },
                    reason="mountain_run_finished",
                    idempotency_key=f"mountain_run_finished:{finished_run.id}",
                    occurred_at=now,
                )
            )
        return MountainRunFinished(
            run=finished_run,
            player_before=player_before,
            player_after=saved_player,
            was_already_finished=False,
        )
