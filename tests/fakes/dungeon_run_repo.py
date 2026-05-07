"""In-memory реализация `IDungeonRunRepository` для unit-тестов use-case-ов.

Зеркало `FakeMountainRunRepository`. Имитирует `SqlAlchemyDungeonRunRepository`
(Спринт 3.1-B): partial unique-индекс `(player_id, status='in_progress')`,
serial id, `IntegrityError` для несуществующего id в `save()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunStatus,
    IDungeonRunRepository,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeDungeonRunRepository(IDungeonRunRepository):
    """In-memory реализация для тестов use-case-ов данжона."""

    rows: list[DungeonRun] = field(default_factory=list)

    async def add(self, run: DungeonRun) -> DungeonRun:
        if run.id is not None:
            raise IntegrityError(f"DungeonRun with pre-set id={run.id} cannot be added; use save()")
        if run.status is DungeonRunStatus.IN_PROGRESS and any(
            existing.player_id == run.player_id and existing.status is DungeonRunStatus.IN_PROGRESS
            for existing in self.rows
        ):
            raise IntegrityError(f"player_id={run.player_id} already has an active dungeon run")
        new_id = (max((r.id or 0 for r in self.rows), default=0)) + 1
        saved = replace(run, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, run_id: int) -> DungeonRun | None:
        for r in self.rows:
            if r.id == run_id:
                return r
        return None

    async def get_active_by_player(self, *, player_id: int) -> DungeonRun | None:
        for r in self.rows:
            if r.player_id == player_id and r.status is DungeonRunStatus.IN_PROGRESS:
                return r
        return None

    async def save(self, run: DungeonRun) -> DungeonRun:
        if run.id is None:
            raise IntegrityError("DungeonRun.save requires id; use add() for new runs")
        for i, existing in enumerate(self.rows):
            if existing.id == run.id:
                self.rows[i] = run
                return run
        raise IntegrityError(f"DungeonRun id={run.id} does not exist")
