"""Часы. Источник «текущего времени» для домена.

Domain-код **никогда** не должен звать `datetime.now()` напрямую — это
делает тесты недетерминированными и ломает воспроизводимость багов.
Вместо этого все use-cases получают `IClock` через DI и зовут `clock.now()`.

В тестах подменяется на `FakeClock` (см. `tests/fakes/clock.py`), который
позволяет «прокручивать» время атомарно.

Кроме UTC-времени порт обязан уметь возвращать «текущую дату по Москве»
(`Europe/Moscow`). Это связано с ГДД §11 (`/oracle`) и §6.1 (Глава клана
дня) — оба механика используют момент «сутки сбросились в 00:00 МСК».
"""

from __future__ import annotations

import abc
from datetime import date, datetime


class IClock(abc.ABC):
    """Интерфейс часов."""

    @abc.abstractmethod
    def now(self) -> datetime:
        """Текущее время в UTC (timezone-aware)."""

    @abc.abstractmethod
    def moscow_date(self) -> date:
        """Текущая календарная дата в `Europe/Moscow`.

        Используется как ключ суточных лимитов (`/oracle`, `clan_daily_head`).
        """
