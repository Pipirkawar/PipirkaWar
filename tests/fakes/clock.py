"""Фейк часов: предсказуемое время с возможностью «прокрутки»."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from pipirik_wars.domain.shared.ports import IClock

_MOSCOW = timezone(timedelta(hours=3), name="Europe/Moscow")


class FakeClock(IClock):
    """In-memory часы.

    >>> clock = FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    >>> clock.now().hour
    12
    >>> clock.advance(hours=2)
    >>> clock.now().hour
    14
    """

    __slots__ = ("_now",)

    def __init__(self, start: datetime | None = None) -> None:
        if start is None:
            start = datetime(2026, 1, 1, tzinfo=UTC)
        if start.tzinfo is None:
            raise ValueError("FakeClock requires timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def moscow_date(self) -> date:
        return self._now.astimezone(_MOSCOW).date()

    def advance(
        self,
        *,
        seconds: float = 0.0,
        minutes: float = 0.0,
        hours: float = 0.0,
        days: float = 0.0,
    ) -> None:
        self._now = self._now + timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)

    def set(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FakeClock.set requires timezone-aware datetime")
        self._now = moment.astimezone(UTC)
