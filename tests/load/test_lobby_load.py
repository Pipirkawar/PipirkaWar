"""Load-тест ``RedisGlobalLobbyRepository`` на FakeRedis (Спринт 4.1-J, J.3).

Сценарий: ``LOAD_OPS_COUNT`` параллельных ``enqueue`` (уникальные
``duel_id``) → последовательное опустошение очереди через
``pop_oldest()`` (FIFO-инвариант). Измеряется p99 как ``enqueue``-а,
так и ``pop_oldest``-а; обе должны уложиться в ``LOAD_P99_BUDGET_MS``.

Бэкенд — ``fakeredis.aioredis.FakeRedis`` (in-process). Lua-скрипты
эмулируются high-fidelity, поэтому профилируем чистый
Python/serialization-overhead без сетевого RTT.
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

from pipirik_wars.infrastructure.redis.repositories.global_lobby import (
    RedisGlobalLobbyRepository,
)
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
def lobby(redis_client: Redis) -> RedisGlobalLobbyRepository:
    """``RedisGlobalLobbyRepository`` на FakeRedis (без метрик в этом сценарии)."""
    return RedisGlobalLobbyRepository(client=redis_client)


async def _enqueue_with_latency(
    lobby: RedisGlobalLobbyRepository,
    duel_id: int,
    enqueued_at: datetime,
    latencies: list[float],
) -> None:
    """Один ``enqueue``-вызов с замером latency."""
    start = time.perf_counter()
    await lobby.enqueue(duel_id=duel_id, enqueued_at=enqueued_at)
    latencies.append(time.perf_counter() - start)


class TestRedisGlobalLobbyLoad:
    """4.1-J / J.3: load-сценарии ``RedisGlobalLobbyRepository``."""

    async def test_enqueue_p99_under_budget(
        self,
        lobby: RedisGlobalLobbyRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """``ops_count`` уникальных ``enqueue`` → p99 < бюджет.

        Параллелим через ``asyncio.gather``. Каждый ``duel_id``
        уникальный, поэтому Lua-скрипт ``enqueue.lua`` всегда
        возвращает 1 (новая запись).
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        latencies: list[float] = []
        await asyncio.gather(
            *(
                _enqueue_with_latency(
                    lobby,
                    duel_id=i,
                    enqueued_at=now + timedelta(seconds=i),
                    latencies=latencies,
                )
                for i in range(ops_count)
            )
        )
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops enqueue scenario"
        )

    async def test_pop_oldest_p99_under_budget(
        self,
        lobby: RedisGlobalLobbyRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """После ``ops_count`` ``enqueue`` — ``ops_count`` последовательных
        ``pop_oldest()`` тоже укладываются в бюджет.

        ``pop_oldest`` — LPOP+HDEL Lua-скрипт, обычно медленнее
        ``enqueue``-а из-за двух команд, поэтому проверяем отдельно.
        FIFO-инвариант проверяется в unit-тестах; здесь только профиль.
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        # Пре-заполняем очередь последовательно (warmup), не замеряя.
        for i in range(ops_count):
            await lobby.enqueue(duel_id=i, enqueued_at=now + timedelta(seconds=i))

        latencies: list[float] = []
        # Опустошаем очередь до конца. Не gather-им — pop_oldest по
        # контракту FIFO-последовательный.
        for _ in range(ops_count):
            start = time.perf_counter()
            entry = await lobby.pop_oldest()
            latencies.append(time.perf_counter() - start)
            assert entry is not None
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops pop_oldest scenario"
        )

    async def test_is_in_lobby_p99_under_budget(
        self,
        lobby: RedisGlobalLobbyRepository,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """``is_in_lobby`` на заполненной очереди тоже укладывается в бюджет.

        Это самый лёгкий вызов (один ``HEXISTS``-roundtrip), профиль
        характеризует «hot read»-сценарий.
        """
        now = datetime(2026, 5, 4, 12, tzinfo=UTC)
        for i in range(ops_count):
            await lobby.enqueue(duel_id=i, enqueued_at=now + timedelta(seconds=i))

        latencies: list[float] = []
        # Все запросы — на существующие duel_id (positive path —
        # самый частый сценарий в продакшене перед ``pop_oldest``).
        for i in range(ops_count):
            start = time.perf_counter()
            present = await lobby.is_in_lobby(duel_id=i)
            latencies.append(time.perf_counter() - start)
            assert present is True
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops is_in_lobby scenario"
        )
