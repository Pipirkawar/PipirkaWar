"""Тесты `FakeClock`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from tests.fakes import FakeClock


class TestFakeClock:
    def test_default_start_is_2026_01_01_utc(self) -> None:
        clock = FakeClock()
        assert clock.now() == datetime(2026, 1, 1, tzinfo=UTC)

    def test_explicit_start_is_normalized_to_utc(self) -> None:
        msk = timezone(timedelta(hours=3))
        clock = FakeClock(datetime(2026, 5, 4, 15, 0, tzinfo=msk))
        assert clock.now() == datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FakeClock(datetime(2026, 1, 1))

    def test_advance_moves_clock_forward(self) -> None:
        clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
        clock.advance(hours=2, minutes=30)
        assert clock.now() == datetime(2026, 1, 1, 2, 30, tzinfo=UTC)

    def test_set_replaces_current_moment(self) -> None:
        clock = FakeClock()
        target = datetime(2027, 6, 15, 10, 0, tzinfo=UTC)
        clock.set(target)
        assert clock.now() == target

    def test_set_naive_raises(self) -> None:
        clock = FakeClock()
        with pytest.raises(ValueError, match="timezone-aware"):
            clock.set(datetime(2027, 1, 1))

    def test_moscow_date_at_midnight_utc_already_in_next_day(self) -> None:
        # 2026-05-04 00:00 UTC == 2026-05-04 03:00 MSK → дата та же
        clock = FakeClock(datetime(2026, 5, 4, 0, 0, tzinfo=UTC))
        assert clock.moscow_date().isoformat() == "2026-05-04"

    def test_moscow_date_late_evening_utc_is_next_day_in_msk(self) -> None:
        # 2026-05-03 22:00 UTC == 2026-05-04 01:00 MSK → дата уже 04
        clock = FakeClock(datetime(2026, 5, 3, 22, 0, tzinfo=UTC))
        assert clock.moscow_date().isoformat() == "2026-05-04"

    def test_moscow_date_before_msk_midnight(self) -> None:
        # 2026-05-03 20:30 UTC == 2026-05-03 23:30 MSK → дата ещё 03
        clock = FakeClock(datetime(2026, 5, 3, 20, 30, tzinfo=UTC))
        assert clock.moscow_date().isoformat() == "2026-05-03"
