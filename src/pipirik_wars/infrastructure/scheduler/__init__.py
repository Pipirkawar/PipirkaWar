"""infrastructure/scheduler package — адаптеры `IDelayedJobScheduler`.

Production-реализация (`APSchedulerDelayedJobScheduler`) использует
APScheduler `AsyncIOScheduler` (Спринт 1.3.C / ПД §1.3.3).
"""

from pipirik_wars.infrastructure.scheduler.aps import APSchedulerDelayedJobScheduler

__all__ = ["APSchedulerDelayedJobScheduler"]
