"""In-memory реализация `IDelayedJobScheduler` для unit-тестов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.shared.ports import IDelayedJobScheduler


@dataclass(frozen=True, slots=True)
class ScheduledFinish:
    """Запись «что и на когда было запланировано»."""

    run_id: int
    run_at: datetime


@dataclass
class FakeDelayedJobScheduler(IDelayedJobScheduler):
    """Фиксирует все вызовы `schedule_finish_forest_run` / `cancel_*`."""

    scheduled: dict[int, ScheduledFinish] = field(default_factory=dict)
    cancelled: list[int] = field(default_factory=list)

    async def schedule_finish_forest_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        self.scheduled[run_id] = ScheduledFinish(run_id=run_id, run_at=run_at)

    async def cancel_finish_forest_run(self, *, run_id: int) -> None:
        self.cancelled.append(run_id)
        self.scheduled.pop(run_id, None)
