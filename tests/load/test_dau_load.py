"""Load-тест ``RedisDauCounter`` на FakeRedis (Спринт 4.1-J, J.3).

Сценарий: ``LOAD_OPS_COUNT`` уникальных игроков параллельно дергают
``record_active(tg_user_id=...)`` через ``asyncio.gather`` + один
``current()`` в конце. На каждой операции — ``time.perf_counter()``-
elapsed; затем считается p99-латенси и проверяется, что она не
превышает ``LOAD_P99_BUDGET_MS``.

FakeRedis даёт high-fidelity-эмуляцию pipeline-а ``ZADD + EXPIRE``,
поэтому профилирование латенси здесь — это профилирование Python-
overhead-а в репозитории + сериализации команд, без сетевого RTT.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.infrastructure.observability import RedisMetrics
from pipirik_wars.infrastructure.redis.repositories.dau import RedisDauCounter
from tests.fakes import FakeClock
from tests.load.conftest import measure_p99

pytestmark = pytest.mark.load

_MOSCOW_TZ = timezone(timedelta(hours=3))


def _msk(year: int, month: int, day: int, hour: int = 12) -> datetime:
    """МСК-момент → UTC-aware datetime."""
    return datetime(year, month, day, hour, tzinfo=_MOSCOW_TZ).astimezone(UTC)


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
    """FakeClock на 4 мая 2026 12:00 МСК — детерминированный day-key `dau:2026-05-04`."""
    return FakeClock(_msk(2026, 5, 4, hour=12))


@pytest.fixture
def counter(redis_client: Redis, clock: FakeClock) -> RedisDauCounter:
    """``RedisDauCounter`` с FakeRedis-backend-ом и FakeClock-ом."""
    return RedisDauCounter(client=redis_client, clock=clock)


@pytest.fixture
def counter_with_metrics(redis_client: Redis, clock: FakeClock) -> RedisDauCounter:
    """``RedisDauCounter`` с инжектированным ``RedisMetrics`` — sanity-вариант.

    Проверяем, что инструментация **не** ухудшает p99 заметно: метрики
    регистрируются в isolated-``CollectorRegistry``-е, чтобы не
    контаминировать глобальный default.
    """
    metrics = RedisMetrics()
    return RedisDauCounter(client=redis_client, clock=clock, metrics=metrics)


async def _record_active_with_latency(
    counter: RedisDauCounter,
    tg_user_id: int,
    latencies: list[float],
) -> None:
    """Один ``record_active``-вызов с замером latency в секундах."""
    start = time.perf_counter()
    await counter.record_active(tg_user_id=tg_user_id)
    latencies.append(time.perf_counter() - start)


class TestRedisDauCounterLoad:
    """4.1-J / J.3: load-сценарии ``RedisDauCounter``."""

    async def test_record_active_p99_under_budget(
        self,
        counter: RedisDauCounter,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """``ops_count`` уникальных ``record_active`` → p99 < бюджет.

        Параллелим через ``asyncio.gather`` (FakeRedis шарит
        in-process state — никаких race-condition-проблем). На каждой
        операции — отдельный ``time.perf_counter()``; p99 считается из
        полного массива на стороне теста.
        """
        latencies: list[float] = []
        await asyncio.gather(
            *(
                _record_active_with_latency(counter, tg_user_id=i, latencies=latencies)
                for i in range(ops_count)
            )
        )
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops record_active scenario"
        )

    async def test_current_after_full_load_returns_exact_count(
        self,
        counter: RedisDauCounter,
        ops_count: int,
    ) -> None:
        """После ``ops_count`` уникальных вставок ``current()`` == ``ops_count``.

        Sanity-инвариант ZSET-а: count = cardinality. Если падает —
        значит pipeline-овая команда теряется на нагрузке (это бы
        был серьёзный регресс atomicity-контракта).
        """
        await asyncio.gather(*(counter.record_active(tg_user_id=i) for i in range(ops_count)))
        assert await counter.current() == ops_count

    async def test_record_active_with_metrics_does_not_blow_p99(
        self,
        counter_with_metrics: RedisDauCounter,
        ops_count: int,
        p99_budget_ms: float,
    ) -> None:
        """Тот же сценарий, но с включёнными Prometheus-метриками.

        Sanity-инвариант observability-overhead-а: ``RedisMetrics.track(...)``
        в горячем пути не должен ронять p99 за пределы бюджета.
        Если падает — значит инструментация прибавляет миллисекунды
        per-op, и её нужно оптимизировать (или поднимать бюджет).
        """
        latencies: list[float] = []
        await asyncio.gather(
            *(
                _record_active_with_latency(counter_with_metrics, tg_user_id=i, latencies=latencies)
                for i in range(ops_count)
            )
        )
        assert len(latencies) == ops_count
        p99_ms = measure_p99(latencies)
        assert p99_ms <= p99_budget_ms, (
            f"p99={p99_ms:.2f}ms (with metrics) exceeds budget={p99_budget_ms:.2f}ms "
            f"on {ops_count}-ops record_active scenario"
        )
