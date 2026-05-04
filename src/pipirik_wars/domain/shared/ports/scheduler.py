"""Порт отложенных задач (`IDelayedJobScheduler`).

Use-case-ы с таймером (`/forest`, `/mountain`, `/dungeon`, `/caravan`)
ставят job на «вернуть игрока» через несколько минут. Реализация
живёт в `infrastructure/scheduler/` — production использует
`AsyncIOScheduler` от APScheduler (ПД §3 / Спринт 1.3.3); в тестах
работает `FakeDelayedJobScheduler` (in-memory список запланированных
job-ов).

Контракты:
- `schedule(...)` идемпотентен по `job_id` (повторный вызов с тем же
  `job_id` перезаписывает существующий job — это нужно для
  recovery-сценариев на старте бота).
- `cancel(...)` — NO-OP, если job-а нет.
- Сам job не получает контекст (uow / repos / etc.) — это
  ответственность infrastructure-адаптера: он замыкает callable вокруг
  contianer-а и при срабатывании вызывает use-case `FinishForestRun`
  с правильными зависимостями.
"""

from __future__ import annotations

import abc
from datetime import datetime


class IDelayedJobScheduler(abc.ABC):
    """Планировщик отложенных задач (минимально нужный набор)."""

    @abc.abstractmethod
    async def schedule_finish_forest_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `FinishForestRun(run_id=...)` на `run_at` (UTC).

        Идемпотентно по `run_id`: повторный вызов перезаписывает job.
        """

    @abc.abstractmethod
    async def cancel_finish_forest_run(self, *, run_id: int) -> None:
        """Снять запланированный finish-job (NO-OP, если его нет)."""
