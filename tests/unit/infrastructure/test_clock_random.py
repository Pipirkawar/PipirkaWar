"""Unit-тесты `RealClock` и `RealRandom`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.random import RealRandom


class TestRealClock:
    def test_now_is_timezone_aware_utc(self) -> None:
        clock = RealClock()
        now = clock.now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    @freeze_time("2026-05-04 23:30:00", tz_offset=0)
    def test_moscow_date_late_evening_utc_is_next_day_msk(self) -> None:
        # 23:30 UTC == 02:30 MSK следующего дня.
        clock = RealClock()
        assert clock.moscow_date() == datetime(2026, 5, 5).date()

    @freeze_time("2026-05-04 12:00:00", tz_offset=0)
    def test_moscow_date_midday_utc_is_same_day_msk(self) -> None:
        clock = RealClock()
        assert clock.moscow_date() == datetime(2026, 5, 4).date()

    @freeze_time("2026-05-04 12:00:00", tz_offset=0)
    def test_now_returns_aware(self) -> None:
        clock = RealClock()
        assert clock.now() == datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


class TestRealRandom:
    def test_randint_inclusive(self) -> None:
        rng = RealRandom()
        for _ in range(100):
            assert 1 <= rng.randint(1, 5) <= 5

    def test_randint_low_gt_high_raises(self) -> None:
        rng = RealRandom()
        with pytest.raises(ValueError):
            rng.randint(5, 1)

    def test_uniform_in_range(self) -> None:
        rng = RealRandom()
        for _ in range(20):
            v = rng.uniform(0.0, 1.0)
            assert 0.0 <= v <= 1.0

    def test_uniform_low_gt_high_raises(self) -> None:
        rng = RealRandom()
        with pytest.raises(ValueError):
            rng.uniform(1.0, 0.0)

    def test_choice_returns_member(self) -> None:
        rng = RealRandom()
        items = ["a", "b", "c"]
        for _ in range(20):
            assert rng.choice(items) in items

    def test_choice_empty_raises(self) -> None:
        rng = RealRandom()
        with pytest.raises(ValueError):
            rng.choice([])

    def test_weighted_choice_returns_member(self) -> None:
        rng = RealRandom()
        items = ["scarce", "normal", "abundant"]
        weights = [50, 35, 15]
        for _ in range(20):
            assert rng.weighted_choice(items, weights) in items

    def test_weighted_choice_validations(self) -> None:
        rng = RealRandom()
        with pytest.raises(ValueError, match="empty"):
            rng.weighted_choice([], [])
        with pytest.raises(ValueError, match="length mismatch"):
            rng.weighted_choice(["a"], [1, 2])
        with pytest.raises(ValueError, match="positive"):
            rng.weighted_choice(["a", "b"], [1, 0])

    def test_deterministic_uint_is_stable(self) -> None:
        rng = RealRandom()
        first = rng.deterministic_uint("clan:42:2026-05-04", 86400)
        second = rng.deterministic_uint("clan:42:2026-05-04", 86400)
        assert first == second
        assert 0 <= first < 86400

    def test_deterministic_uint_modulo_validation(self) -> None:
        rng = RealRandom()
        with pytest.raises(ValueError, match="positive"):
            rng.deterministic_uint("seed", 0)

    def test_deterministic_uint_distinct_seeds(self) -> None:
        rng = RealRandom()
        a = rng.deterministic_uint("seed-1", 1_000_000)
        b = rng.deterministic_uint("seed-2", 1_000_000)
        assert a != b
