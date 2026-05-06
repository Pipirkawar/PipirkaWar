"""Use-case `ScheduleDailyHeadCronJobs` — пересоздание per-clan APScheduler-job-ов
для cron-триггера «Главы клана дня» (Спринт 2.3.F.2).

Зачем:
- На каждые сутки у каждого активного клана должен быть запланирован один
  APScheduler-job, срабатывающий в `00:00 МСК + offset(clan_id, date)`.
- `offset` детерминирован (`compute_daily_head_cron_offset_minutes`), но
  меняется день за днём — поэтому мы перепланируем job-ы ежедневно.
- Frozen / архивированные кланы исключаются (через
  `IClanRepository.list_active`) — для них cron-у нечего делать.

Точки вызова:
1. **Bootstrap при старте бота** (`bot/main.py.run()`): сразу после
   `scheduler.start()` зовём этот use-case, чтобы пере-зарегистрировать
   сегодняшние job-ы (in-memory job-store APScheduler чистый при рестарте).
2. **Daily reschedule** в 00:00 МСК через сам APScheduler — отдельная
   `cron`-задача в `bot/main.py` зовёт этот use-case на новые сутки.

Семантика:
- Если для клана `run_at <= now`, скипаем — кнопка `/clan_head` уже
  доступна, cron на сегодня «не успел».
- Если для клана уже есть запланированный job (с тем же id) — APScheduler
  его перезапишет (`replace_existing=True`).
- Use-case возвращает `ScheduleDailyHeadCronJobsResult(scheduled, skipped)`
  для логов / тестов.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.daily_head import compute_daily_head_cron_run_at_utc
from pipirik_wars.domain.shared.ports import (
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class ScheduleDailyHeadCronJobsResult:
    """Что сделал `ScheduleDailyHeadCronJobs.execute()`."""

    scheduled: tuple[int, ...]
    """`clan_id`-ы, для которых поставлен job (в UTC `>` now)."""

    skipped_past: tuple[int, ...]
    """`clan_id`-ы, у которых сегодняшний `run_at` уже прошёл (`<= now`)."""

    skipped_no_id: tuple[int, ...]
    """`clan_id`-ы, у которых `clan.id is None` (защита от мусорных строк)."""


class ScheduleDailyHeadCronJobs:
    """Перепланировать сегодняшние per-clan cron-job-ы «Главы клана дня»."""

    __slots__ = ("_clans", "_clock", "_scheduler", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        scheduler: IDelayedJobScheduler,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._scheduler = scheduler
        self._clock = clock

    async def execute(self) -> ScheduleDailyHeadCronJobsResult:
        """Поставить APScheduler-job для каждого активного клана на сегодня.

        Один проход по `clans.list_active()` внутри активного UoW
        (read-only, без коммита side-effect-ов в БД). Каждое
        `scheduler.schedule_daily_head_cron(...)` идемпотентно по `clan_id`.
        """
        now = self._clock.now()
        moscow_date = self._clock.moscow_date()
        scheduled: list[int] = []
        skipped_past: list[int] = []
        skipped_no_id: list[int] = []

        async with self._uow:
            active_clans = await self._clans.list_active()

        for clan in active_clans:
            clan_id = clan.id
            if clan_id is None:
                # Защита от мусора — `list_active` обязан возвращать
                # только записи с `id`, но контракт лучше закрепить.
                skipped_no_id.append(0)
                continue
            run_at = compute_daily_head_cron_run_at_utc(
                clan_id=clan_id,
                moscow_date=moscow_date,
            )
            if run_at <= now:
                skipped_past.append(clan_id)
                continue
            await self._scheduler.schedule_daily_head_cron(
                clan_id=clan_id,
                run_at=run_at,
            )
            scheduled.append(clan_id)

        return ScheduleDailyHeadCronJobsResult(
            scheduled=tuple(scheduled),
            skipped_past=tuple(skipped_past),
            skipped_no_id=tuple(skipped_no_id),
        )


__all__ = [
    "ScheduleDailyHeadCronJobs",
    "ScheduleDailyHeadCronJobsResult",
]
