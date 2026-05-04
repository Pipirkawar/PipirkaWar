"""Unit-тесты `InMemoryTokenBucketRateLimiter`."""

from __future__ import annotations

import pytest

from pipirik_wars.infrastructure.rate_limit import InMemoryTokenBucketRateLimiter
from tests.fakes import FakeClock


class TestTokenBucket:
    def test_initial_capacity_allows_n_requests(self) -> None:
        limiter = InMemoryTokenBucketRateLimiter(
            capacity=5, refill_per_second=0.1, clock=FakeClock()
        )
        for _ in range(5):
            assert limiter.try_acquire(key="player:1") is True
        # 6-й — отказ.
        assert limiter.try_acquire(key="player:1") is False

    def test_separate_keys_have_separate_buckets(self) -> None:
        limiter = InMemoryTokenBucketRateLimiter(
            capacity=2, refill_per_second=0.1, clock=FakeClock()
        )
        assert limiter.try_acquire(key="player:1") is True
        assert limiter.try_acquire(key="player:1") is True
        assert limiter.try_acquire(key="player:1") is False
        # Другой ключ — ещё свежий.
        assert limiter.try_acquire(key="player:2") is True

    def test_refills_over_time(self) -> None:
        clock = FakeClock()
        limiter = InMemoryTokenBucketRateLimiter(capacity=1, refill_per_second=1.0, clock=clock)
        assert limiter.try_acquire(key="k") is True
        assert limiter.try_acquire(key="k") is False
        # Через 2 секунды — токен снова доступен (capacity capped at 1).
        clock.advance(seconds=2)
        assert limiter.try_acquire(key="k") is True
        assert limiter.try_acquire(key="k") is False

    def test_ten_per_second_eleventh_rejected(self) -> None:
        """Спринт 0.2.7 acceptance: 10 команд за секунду — 11-я отказана."""
        clock = FakeClock()
        limiter = InMemoryTokenBucketRateLimiter(capacity=10, refill_per_second=10.0, clock=clock)
        for _ in range(10):
            assert limiter.try_acquire(key="player:1") is True
        # Без advance — 11-я падает.
        assert limiter.try_acquire(key="player:1") is False

    def test_capacity_validation(self) -> None:
        with pytest.raises(ValueError):
            InMemoryTokenBucketRateLimiter(capacity=0, refill_per_second=1.0, clock=FakeClock())

    def test_refill_validation(self) -> None:
        with pytest.raises(ValueError):
            InMemoryTokenBucketRateLimiter(capacity=1, refill_per_second=0.0, clock=FakeClock())
