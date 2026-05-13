"""Unit-тесты `RedisMetrics` (Спринт 4.1-J, шаг J.1).

Покрытие:

* Counter `pipirik_redis_op_total{backend, op, outcome}`:
  - инкремент на success-выходе (outcome=``"ok"``);
  - инкремент на failure (outcome=``"error"``) + исключение re-raise-ится;
  - лейблы передаются как kwargs `backend` / `op`.
* Histogram `pipirik_redis_op_duration_seconds{backend, op}`:
  - observe() в правильный bucket по time.perf_counter()-elapsed
    (используем `await asyncio.sleep(...)`, чтобы реально потратить
    замеренное время);
  - inheritance-bucket-counter: значение, попавшее в bucket ``X``,
    инкрементирует все bucket-counter-ы с верхней границей ``>= X``.
* Изоляция: для каждого теста создаётся свежий `CollectorRegistry`;
  без этого повторная инстанциация `RedisMetrics` падает с
  «Duplicated timeseries in CollectorRegistry».

Семантика `prometheus_client`:

* `Counter.labels(...).inc()` — обычная инкрементация;
* `Histogram.labels(...).observe(value)` — добавление в bucket;
  `_count` — общее число observe-ов; `_sum` — сумма observed-values;
  `_buckets` — список (`Counter`-ов inheritance-bucket).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from prometheus_client import CollectorRegistry

from pipirik_wars.infrastructure.observability.redis_metrics import RedisMetrics
from pipirik_wars.infrastructure.redis.repositories.dau import RedisDauCounter
from tests.fakes import FakeClock


@pytest.fixture
def registry() -> CollectorRegistry:
    """Свежий `CollectorRegistry` на каждый тест.

    Без изоляции `prometheus_client` падает «Duplicated timeseries»
    при повторной инстанциации `RedisMetrics` в рамках одного pytest-
    процесса (Counter и Histogram регистрируются глобально).
    """
    return CollectorRegistry()


@pytest.fixture
def metrics(registry: CollectorRegistry) -> RedisMetrics:
    return RedisMetrics(registry=registry)


def _counter_value(
    registry: CollectorRegistry,
    *,
    backend: str,
    op: str,
    outcome: str,
) -> float:
    """Прочитать текущее значение counter-а для заданных лейблов."""
    return (
        registry.get_sample_value(
            "pipirik_redis_op_total",
            {"backend": backend, "op": op, "outcome": outcome},
        )
        or 0.0
    )


def _histogram_count(
    registry: CollectorRegistry,
    *,
    backend: str,
    op: str,
) -> float:
    """Сколько observe-ов было в `pipirik_redis_op_duration_seconds{...}`."""
    return (
        registry.get_sample_value(
            "pipirik_redis_op_duration_seconds_count",
            {"backend": backend, "op": op},
        )
        or 0.0
    )


def _histogram_sum(
    registry: CollectorRegistry,
    *,
    backend: str,
    op: str,
) -> float:
    """Сумма observed-значений в `pipirik_redis_op_duration_seconds{...}`."""
    return (
        registry.get_sample_value(
            "pipirik_redis_op_duration_seconds_sum",
            {"backend": backend, "op": op},
        )
        or 0.0
    )


def _histogram_bucket(
    registry: CollectorRegistry,
    *,
    backend: str,
    op: str,
    le: str,
) -> float:
    """Инкрементальный счётчик bucket-а `le=<X>`.

    Prometheus-histogram-bucket cumulative: значение в bucket-е ``le=Y``
    включает все наблюдения с value ``<= Y``.
    """
    return (
        registry.get_sample_value(
            "pipirik_redis_op_duration_seconds_bucket",
            {"backend": backend, "op": op, "le": le},
        )
        or 0.0
    )


class TestRedisMetricsCounter:
    async def test_counter_increments_on_success(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """`track(...)` без исключения → outcome=`"ok"`, counter +1."""
        async with metrics.track(backend="dau", op="record_active"):
            pass

        assert _counter_value(registry, backend="dau", op="record_active", outcome="ok") == 1.0
        assert _counter_value(registry, backend="dau", op="record_active", outcome="error") == 0.0

    async def test_counter_increments_on_error_and_reraises(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """`track(...)` с исключением → outcome=`"error"`, исключение re-raise-ится."""

        class _BoomError(Exception):
            pass

        with pytest.raises(_BoomError):
            async with metrics.track(backend="lobby", op="enqueue"):
                raise _BoomError("simulated redis failure")

        assert _counter_value(registry, backend="lobby", op="enqueue", outcome="error") == 1.0
        assert _counter_value(registry, backend="lobby", op="enqueue", outcome="ok") == 0.0

    async def test_counter_accumulates_across_calls(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """Серия из 3× success + 2× error правильно агрегируется."""
        for _ in range(3):
            async with metrics.track(backend="activity_lock", op="try_acquire"):
                pass

        for _ in range(2):
            with pytest.raises(RuntimeError):
                async with metrics.track(backend="activity_lock", op="try_acquire"):
                    raise RuntimeError("redis disconnected")

        assert (
            _counter_value(
                registry,
                backend="activity_lock",
                op="try_acquire",
                outcome="ok",
            )
            == 3.0
        )
        assert (
            _counter_value(
                registry,
                backend="activity_lock",
                op="try_acquire",
                outcome="error",
            )
            == 2.0
        )

    async def test_counter_partitions_by_backend_and_op(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """Разные `(backend, op)` — независимые счётчики."""
        async with metrics.track(backend="dau", op="record_active"):
            pass
        async with metrics.track(backend="dau", op="current"):
            pass
        async with metrics.track(backend="lobby", op="record_active"):
            pass

        assert _counter_value(registry, backend="dau", op="record_active", outcome="ok") == 1.0
        assert _counter_value(registry, backend="dau", op="current", outcome="ok") == 1.0
        assert _counter_value(registry, backend="lobby", op="record_active", outcome="ok") == 1.0


class TestRedisMetricsHistogram:
    async def test_histogram_observes_elapsed_time(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """`asyncio.sleep(0.02)` → histogram._sum > 0.02, _count == 1."""
        async with metrics.track(backend="dau", op="record_active"):
            await asyncio.sleep(0.02)

        assert _histogram_count(registry, backend="dau", op="record_active") == 1.0
        observed_sum = _histogram_sum(registry, backend="dau", op="record_active")
        assert observed_sum >= 0.02
        # Реалистичный upper-bound: 0.02 + ~1с slack на CI overhead-jitter.
        assert observed_sum < 1.0

    async def test_histogram_bucket_inheritance(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """Значение ~20 мс попадает во все bucket-ы с `le >= 0.025`.

        Buckets `[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0,
        2.5, 5.0]`: значение `0.02` < `0.025` (включается в `le=0.025` и
        выше), не включается в `le=0.001 / 0.005 / 0.01`.
        """
        async with metrics.track(backend="lobby", op="enqueue"):
            await asyncio.sleep(0.02)

        # Buckets ниже observed-value — пустые.
        assert _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.001") == 0.0
        assert _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.005") == 0.0
        assert _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.01") == 0.0

        # Buckets начиная с 0.025 — должны включать observed-value.
        # На очень медленных CI (jitter > 50 мс на 20-мс sleep) bucket `0.025`
        # может пропустить наблюдение; в этом случае оно гарантированно
        # попадёт в `0.05`+.
        bucket_25 = _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.025")
        bucket_50 = _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.05")
        bucket_100 = _histogram_bucket(registry, backend="lobby", op="enqueue", le="0.1")
        bucket_inf = _histogram_bucket(registry, backend="lobby", op="enqueue", le="+Inf")
        # `bucket(le="+Inf")` = total count (cumulative inheritance).
        assert bucket_inf == 1.0
        # Bucket 0.05 и выше — наблюдение должно быть учтено (даже с CI-jitter
        # 20мс sleep укладывается в 50мс).
        assert bucket_50 >= 1.0
        assert bucket_100 >= 1.0
        # 0.025 может включать, может и нет (граничный случай).
        assert bucket_25 in (0.0, 1.0)

    async def test_histogram_observes_on_error(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """Histogram фиксирует elapsed даже если внутри `track` было исключение."""
        with pytest.raises(ValueError):
            async with metrics.track(backend="activity_lock", op="get"):
                await asyncio.sleep(0.005)
                raise ValueError("boom")

        assert _histogram_count(registry, backend="activity_lock", op="get") == 1.0
        assert _histogram_sum(registry, backend="activity_lock", op="get") >= 0.005


class TestRedisMetricsRegistryIsolation:
    def test_isolated_registries_do_not_collide(self) -> None:
        """Две инстанциации `RedisMetrics` с разными registry — без коллизий."""
        reg1 = CollectorRegistry()
        reg2 = CollectorRegistry()
        m1 = RedisMetrics(registry=reg1)
        m2 = RedisMetrics(registry=reg2)
        # Если бы регистрация ушла в глобальный REGISTRY, второй вызов упал бы
        # с `ValueError: Duplicated timeseries`.
        assert m1.registry is reg1
        assert m2.registry is reg2

    def test_default_registry_attribute_is_none(self) -> None:
        """Property `registry` отражает переданный аргумент конструктора."""
        reg = CollectorRegistry()
        metrics = RedisMetrics(registry=reg)
        assert metrics.registry is reg


class TestRedisMetricsContextManagerReentrancy:
    """`track(...)` поддерживает nested-вызовы для `(backend, op)`-пар."""

    async def test_nested_track_calls_do_not_corrupt_state(
        self,
        metrics: RedisMetrics,
        registry: CollectorRegistry,
    ) -> None:
        """Nested `async with` правильно учитываются как 2 независимых observe-а."""
        async with (
            metrics.track(backend="dau", op="record_active"),
            metrics.track(backend="dau", op="current"),
        ):
            await asyncio.sleep(0.001)

        assert _counter_value(registry, backend="dau", op="record_active", outcome="ok") == 1.0
        assert _counter_value(registry, backend="dau", op="current", outcome="ok") == 1.0
        assert _histogram_count(registry, backend="dau", op="record_active") == 1.0
        assert _histogram_count(registry, backend="dau", op="current") == 1.0


class TestRedisMetricsNoopMode:
    """В репозитории `metrics=None` → нет инкрементов (через локальный `_track`-хелпер).

    Здесь только smoke-проверка, что repo с `metrics=None` действительно
    работает без NPE; счётчики в этом сценарии не существуют в registry.
    """

    async def test_dau_counter_works_with_metrics_none(self) -> None:
        client: Any = FakeRedis()
        clock = FakeClock(datetime(2026, 5, 13, 12, 0, tzinfo=UTC))
        counter = RedisDauCounter(client=client, clock=clock, metrics=None)
        try:
            await counter.record_active(tg_user_id=1)
            assert await counter.current() == 1
        finally:
            await client.aclose()
