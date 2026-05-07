"""In-memory реализация `IMountainRunRepository` для unit-тестов use-case-ов.

Имитирует ключевое поведение `SqlAlchemyMountainRunRepository` (Спринт 3.1-B):
- `add()` без `id` присваивает следующий serial и возвращает копию с `id`;
- partial unique-индекс `(player_id, status='in_progress')` — попытка
  `add()` второй активной записи на того же игрока бросает `IntegrityError`;
- `get_active_by_player()` возвращает только запись со статусом
  `IN_PROGRESS`, иначе `None`;
- `save()` обновляет запись по `id` (используется в `FinishMountainRun`).
  Отсутствующий id — `IntegrityError`.

Не моделирует «откат» при rollback (для этого есть `FakeUnitOfWork`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pipirik_wars.domain.mountains import (
    IMountainRunRepository,
    MountainRun,
    MountainRunStatus,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeMountainRunRepository(IMountainRunRepository):
    """In-memory реализация для тестов use-case-ов гор."""

    rows: list[MountainRun] = field(default_factory=list)

    async def add(self, run: MountainRun) -> MountainRun:
        if run.id is not None:
            raise IntegrityError(
                f"MountainRun with pre-set id={run.id} cannot be added; use save()"
            )
        # Имитация partial unique-индекса: один активный поход на игрока.
        if run.status is MountainRunStatus.IN_PROGRESS and any(
            existing.player_id == run.player_id and existing.status is MountainRunStatus.IN_PROGRESS
            for existing in self.rows
        ):
            raise IntegrityError(f"player_id={run.player_id} already has an active mountain run")
        new_id = (max((r.id or 0 for r in self.rows), default=0)) + 1
        saved = replace(run, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, run_id: int) -> MountainRun | None:
        for r in self.rows:
            if r.id == run_id:
                return r
        return None

    async def get_active_by_player(self, *, player_id: int) -> MountainRun | None:
        for r in self.rows:
            if r.player_id == player_id and r.status is MountainRunStatus.IN_PROGRESS:
                return r
        return None

    async def save(self, run: MountainRun) -> MountainRun:
        if run.id is None:
            raise IntegrityError("MountainRun.save requires id; use add() for new runs")
        for i, existing in enumerate(self.rows):
            if existing.id == run.id:
                self.rows[i] = run
                return run
        raise IntegrityError(f"MountainRun id={run.id} does not exist")
