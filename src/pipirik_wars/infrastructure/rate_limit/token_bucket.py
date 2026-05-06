"""Token-bucket rate-limiter."""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.domain.shared.ports.rate_limiter import IRateLimiter

__all__ = ["IRateLimiter", "InMemoryTokenBucketRateLimiter"]


@dataclass(slots=True)
class _Bucket:
    tokens: float
    last_refill_at: float  # epoch seconds


class InMemoryTokenBucketRateLimiter(IRateLimiter):
    """Простой token-bucket per-key.

    `capacity` — максимум токенов; `refill_per_second` — скорость
    долива. На каждом запросе бакет «доливается» до `capacity` исходя
    из прошедшего времени, затем тратится один токен.

    Не thread-safe и не process-safe — это сознательное упрощение для
    Спринта 0.2. Под aiogram-singleton-процесс хватает; для multi-worker
    деплоя нужен Redis (Спринт 2.x).
    """

    __slots__ = ("_buckets", "_capacity", "_clock", "_refill_per_second")

    def __init__(
        self,
        *,
        capacity: int,
        refill_per_second: float,
        clock: IClock,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def try_acquire(self, *, key: str) -> bool:
        now = self._clock.now().timestamp()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(self._capacity - 1), last_refill_at=now)
            self._buckets[key] = bucket
            return True
        # Долив.
        elapsed = max(0.0, now - bucket.last_refill_at)
        bucket.tokens = min(
            float(self._capacity),
            bucket.tokens + elapsed * self._refill_per_second,
        )
        bucket.last_refill_at = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False
