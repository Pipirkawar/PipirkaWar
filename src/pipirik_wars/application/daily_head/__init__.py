"""Application use-cases «Глава клана дня» (Спринт 2.3.C).

Поверх доменного `DailyHeadService` (2.3.A) и репозиториев 2.3.B —
два триггера, оба идемпотентны по `(clan_id, moscow_date)`:

- `RequestDailyHead` — игрок нажал кнопку «🎲 Назначить главу дня»
  / ввёл `/clan_head` в клан-чате (источник `DailyHeadSource.BUTTON`);
- `RunDailyHeadCron` — APScheduler-cron в `random_offset(0..24h)`-час
  с 00:00 МСК (источник `DailyHeadSource.CRON`).

Оба зовут `DailyHeadService.assign_or_get(...)` и при первом успехе:
- пишут запись в `daily_heads` (UNIQUE-индекс ловит race);
- начисляют бонус через `ILengthGranter.grant(source=DAILY_HEAD)`;
- пишут отдельный `AuditAction.DAILY_HEAD_ASSIGN` сверх стандартного
  `LENGTH_GRANT`-аудита.

Race-handling (`DailyHeadAlreadyAssignedError` от `heads.add(...)`)
конвертируется в идемпотентный возврат записи победителя.
"""

from __future__ import annotations

from pipirik_wars.application.daily_head.dto import DailyHeadResolved
from pipirik_wars.application.daily_head.request import RequestDailyHead
from pipirik_wars.application.daily_head.run_cron import RunDailyHeadCron

__all__ = [
    "DailyHeadResolved",
    "RequestDailyHead",
    "RunDailyHeadCron",
]
