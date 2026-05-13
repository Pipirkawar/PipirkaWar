"""Load-тест ``RedisActivityLockRepository`` на FakeRedis (Спринт 4.1-J, J.3).

Сценарий: ``LOAD_OPS_COUNT`` параллельных ``try_acquire`` (уникальные
``(actor_kind, actor_id)``) → последовательное снятие через
``release()``. Между ``try_acquire`` и ``release`` — серия ``get()``-
вызовов для измерения «hot read»-профиля.

Бэкенд — ``fakeredis.aioredis.FakeRedis`` (in-process). Атомарные
команды ``SET NX PX`` и MULTI/EXEC-pipeline (``GET + PTTL``)
эмулируются high-fidelity.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.domain.security.entities import LockReason
from pipirik_wars.infrastructure.redis.repositories.activity_lock import (
    RedisActivityLockRepository,
)
from tests.fakes import FakeClock
from tests.load.conftest import measure_p99

pytestmark = pytest.mark.load


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    """FakeRedis-инстанс на тест; закрывается в teardown."""
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest.fixture
def clock() -> FakeClock:
    """FakeClock — фиксированный момент времени."""
    return FakeClock(datetime(2026, 5, 4, 12, tzinfo=UTC))


@pytest.fixture
def locks(redis_client: Redis, clock: FakeClock) -> RedisActivityLockRepository:
    """``RedisActivityLockRepository`` на FakeRedis (без метрик в этом сценарии)."""
    return RedisActivityLockRepository(client=redis_client, clock=clock)


async def _try_acquire_with_latency(
    locks: RedisActivityLockRepository,
    actor_id: int,
    now: datetime,
    expires_at: datetime,
    latencies: list[float],
) -> None:
    """Один ``try_acquire``-вызов с замером latency."""
    start = time.perf_counter()
    await locks.try_acquire(
        actor_kind="player",
        actor_id=actor_id,
        reason=LockReason.FOREST,
        now=now,
        expires_at=expires_at,
    )
    latencies.append(time.perf_counter() - start)


class TestRedisActivityLockLoad:
    """4.1-J / J.3: load-сценарии ``RedisActivityLockRepository``."""

    async def test_try_acquire_p99_under_budget(
        self,
        locks: RedisActivityLockRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """``ops_count`` уникальных ``try_acquire`` → p99 < бюджет.

        Параллелим через ``asyncio.gather``. Каждый ``actor_id``
        уникальный, поэтому ``SET NX PX`` всегда успешный (нет
        contention-а на тех же ключах).
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        expires_at = now + timedelta(minutes=5)
        latencies: list[float] = []
        await asyncio.gather(
            *(
                _try_acquire_with_latency(
                    locks,
                    actor_id=i,
                    now=now,
                    expires_at=expires_at,
                    latencies=latencies,
                )
                for i in range(ops_count)
            )
        )
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops try_acquire scenario"
        )

    async def test_release_p99_under_budget(
        self,
        locks: RedisActivityLockRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """После ``ops_count`` ``try_acquire`` параллельный ``release`` укладывается.

        ``release`` — это ``DEL key``, самая лёгкая операция. p99 здесь
        должна быть самой низкой среди трёх операций; если выше
        ``try_acquire``-а — это аномалия.
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        expires_at = now + timedelta(minutes=5)
        # Warmup — последовательное заполнение, не замеряем.
        for i in range(ops_count):
            await locks.try_acquire(
                actor_kind="player",
                actor_id=i,
                reason=LockReason.FOREST,
                now=now,
                expires_at=expires_at,
            )

        latencies: list[float] = []

        async def _release_with_latency(actor_id: int) -> None:
            start = time.perf_counter()
            await locks.release(actor_kind="player", actor_id=actor_id)
            latencies.append(time.perf_counter() - start)

        await asyncio.gather(*(_release_with_latency(i) for i in range(ops_count)))
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops release scenario"
        )

    async def test_get_p99_under_budget(
        self,
        locks: RedisActivityLockRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """``get()`` на заполненной БД (MULTI/EXEC GET+PTTL) укладывается в бюджет.

        Это самый дорогой read-сценарий — pipeline из двух команд +
        JSON-десериализация payload-а. Если падает — это явный
        кандидат на оптимизацию (cache-rate или per-op-profile).
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        expires_at = now + timedelta(minutes=5)
        # Pre-fill: каждый actor_id с активным lock-ом.
        for i in range(ops_count):
            await locks.try_acquire(
                actor_kind="player",
                actor_id=i,
                reason=LockReason.FOREST,
                now=now,
                expires_at=expires_at,
            )

        latencies: list[float] = []

        async def _get_with_latency(actor_id: int) -> None:
            start = time.perf_counter()
            lock = await locks.get(actor_kind="player", actor_id=actor_id)
            latencies.append(time.perf_counter() - start)
            assert lock is not None

        await asyncio.gather(*(_get_with_latency(i) for i in range(ops_count)))
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops get scenario"
        )
