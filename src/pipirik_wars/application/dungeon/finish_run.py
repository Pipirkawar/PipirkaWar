"""Use-case `FinishDungeonRun` (Спринт 3.1-B).

Зеркало `FinishMountainRun`. Отличия:

- `LockReason.DUNGEON`, `AuditAction.DUNGEON_RUN_FINISHED`,
  `AuditSource.DUNGEON`.
- `idempotency_key` use-case-а: `dungeon_run_finished:{run.id}`;
- `idempotency_key` прибавки: `add_length:dungeon_run:{run.id}`;
- `idempotency_key` вычета: `dungeon_run_loss_revoke:{run.id}`.

Контракт идентичен: транзакционность, идемпотентность, gain через
`ILengthGranter` / loss через прямой `with_length`. См. docstring
`FinishMountainRun` для полного описания.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import FinishDungeonRunInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunNotFoundError,
    DungeonRunStatus,
    IDungeonRunRepository,
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
class DungeonRunFinished:
    """Результат финиша. Используется bot-handler-ом (Спринт 3.1-E)."""

    run: DungeonRun
    player_before: Player
    player_after: Player
    was_already_finished: bool


class FinishDungeonRun:
    """Use-case «применить результат похода в данжон и снять блок»."""

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
        runs: IDungeonRunRepository,
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

    async def execute(self, input_dto: FinishDungeonRunInput) -> DungeonRunFinished:
        """Финишировать поход в данжон. См. docstring модуля для контракта."""
        async with self._uow:
            run = await self._runs.get_by_id(run_id=input_dto.run_id)
            if run is None:
                raise DungeonRunNotFoundError(run_id=input_dto.run_id)

            player = await self._players.get_by_id(player_id=run.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=run.player_id)

            if run.status is DungeonRunStatus.FINISHED:
                return DungeonRunFinished(
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
                    source=AuditSource.DUNGEON,
                    reason="dungeon_run_finished",
                    idempotency_key=f"add_length:dungeon_run:{run.id}",
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
                        reason="dungeon_run_loss",
                        idempotency_key=f"dungeon_run_loss_revoke:{run.id}",
                        occurred_at=now,
                        source=AuditSource.DUNGEON,
                        delta_cm=run.length_delta_cm,
                    )
                )

            saved_player = await self._players.get_by_id(player_id=player.id) or player
            finished_run = await self._runs.save(run.mark_finished(finished_at=now))

            await self._locks.release(actor_kind="player", actor_id=run.player_id)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.DUNGEON_RUN_FINISHED,
                    actor_id=player.tg_id,
                    target_kind="dungeon_run",
                    target_id=str(finished_run.id),
                    before={"status": DungeonRunStatus.IN_PROGRESS.value},
                    after={
                        "status": DungeonRunStatus.FINISHED.value,
                        "branch_name": finished_run.branch_name,
                        "length_delta_cm": finished_run.length_delta_cm,
                        "drops_count": len(finished_run.drops),
                        "finished_at": (
                            finished_run.finished_at.isoformat()
                            if finished_run.finished_at is not None
                            else None
                        ),
                    },
                    reason="dungeon_run_finished",
                    idempotency_key=f"dungeon_run_finished:{finished_run.id}",
                    occurred_at=now,
                )
            )
        return DungeonRunFinished(
            run=finished_run,
            player_before=player_before,
            player_after=saved_player,
            was_already_finished=False,
        )
