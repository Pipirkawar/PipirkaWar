"""Production-часы поверх `datetime.now(UTC)` + `zoneinfo`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pipirik_wars.domain.shared.ports import IClock

_MOSCOW = ZoneInfo("Europe/Moscow")


class RealClock(IClock):
    """Системные часы. Никаких сюрпризов.

    Не зовёт `datetime.now()` без `tz` — это неявный naive-datetime,
    запрещён mypy-strict (всегда возвращаем aware-объекты).
    """

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def moscow_date(self) -> date:
        return datetime.now(_MOSCOW).date()
