"""Prometheus-метрики Redis-операций (Спринт 4.1-J, шаг J.1).

Класс `RedisMetrics` инкапсулирует две Prometheus-метрики:

* counter ``pipirik_redis_op_total{backend, op, outcome}`` — счётчик
  завершённых Redis-операций. `backend` — `"activity_lock"` / `"lobby"`
  / `"dau"`. `op` — логическое имя метода репозитория
  (`record_active`, `enqueue`, `try_acquire`, ...). `outcome` —
  `"ok"` при штатном завершении / `"error"` при выброшенном
  исключении.
* histogram ``pipirik_redis_op_duration_seconds{backend, op}`` —
  гистограмма длительности операций. Buckets фиксированы:
  ``[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]``
  секунд (от 1 мс до 5 с — диапазон, в который должны попадать
  все «здоровые» Redis-операции; за пределами 5 с — это уже
  catastrophic regression и попадает в overflow-bucket `+Inf`).

API:

* ``track(backend, op)`` — async-context-manager, который меряет
  `time.perf_counter()`-elapsed внутри `__aenter__`/`__aexit__`
  и в `finally`-блоке инкрементирует counter + observe гистограмму.
  Если внутри `async with`-блока вылетит исключение — outcome=`"error"`,
  и исключение re-raise-ится дальше (контекст-менеджер ничего не
  глотает). Это критично для observability: метрики должны фиксировать
  факт ошибки, но не маскировать её.

Гранулярность — logical-op-level (`backend=dau, op=record_active`),
а не raw-command-level (`zadd`/`expire`): MULTI/EXEC-pipeline и
Lua-скрипт — это один Redis-round-trip и одна атомарная операция;
профилировать их покомандно бессмысленно. Logical-op-level даёт
осмысленную SLO-семантику («сколько в среднем занимает enqueue» — в
8 раз информативнее, чем «сколько занимает HEXISTS»).

Регистрация метрик: по умолчанию идёт в глобальный
``prometheus_client.REGISTRY``. Для unit-тестов передаётся
изолированный `CollectorRegistry` через параметр конструктора
(`RedisMetrics(registry=...)`) — это снимает ошибку «Duplicated
timeseries in CollectorRegistry» при повторной инстанциации
`RedisMetrics` внутри одного pytest-процесса.

Совместимость с no-op-режимом: в трёх Redis-репозиториях
(`RedisActivityLockRepository`, `RedisGlobalLobbyRepository`,
`RedisDauCounter`) параметр конструктора ``metrics`` —
``RedisMetrics | None``; при ``metrics=None`` репозиторий пропускает
обёртку `async with` через локальный `_track`-хелпер, выдающий пустой
`asynccontextmanager`. Это сохраняет нулевой оверхед в тестах и в
sql-default-конфигурации, которая Prometheus вообще не требует.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Final

from prometheus_client import CollectorRegistry, Counter, Histogram

__all__ = ["RedisMetrics"]

# Buckets подобраны под Redis-операционные SLA: 1мс — однокомандный
# `GET`/`SET` на localhost; 100мс — верхняя граница «здоровой» MULTI/EXEC
# через сеть; 1с — порог тревоги; 5с — overflow. Pipeline-операции и
# Lua-скрипты должны укладываться в 0.01-0.1с при MVP-нагрузке.
_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
)


class RedisMetrics:
    """Prometheus-метрики Redis-операций (Спринт 4.1-J, J.1).

    Создавай один экземпляр на процесс и пробрасывай его в три
    Redis-репозитория через параметр конструктора. В unit-тестах
    каждой инстанциации передавай свежий `CollectorRegistry()`,
    чтобы избежать «Duplicated timeseries» между тестами.
    """

    __slots__ = ("_counter", "_histogram", "_registry")

    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        self._registry = registry
        self._counter = Counter(
            "pipirik_redis_op_total",
            "Total Redis operations completed, partitioned by backend/op/outcome.",
            labelnames=("backend", "op", "outcome"),
            registry=registry,
        )
        self._histogram = Histogram(
            "pipirik_redis_op_duration_seconds",
            "Duration of Redis operations in seconds, partitioned by backend/op.",
            labelnames=("backend", "op"),
            buckets=_DURATION_BUCKETS,
            registry=registry,
        )

    @property
    def registry(self) -> CollectorRegistry | None:
        """`CollectorRegistry`, в котором зарегистрированы метрики.

        ``None`` означает, что метрики живут в глобальном
        ``prometheus_client.REGISTRY`` (production-default).
        Возвращается изолированный экземпляр — в unit-тестах
        используется для ``generate_latest(registry)`` без шума
        от других тестов.
        """
        return self._registry

    @asynccontextmanager
    async def track(self, *, backend: str, op: str) -> AsyncIterator[None]:
        """Замерить длительность операции и обновить метрики.

        Использование::

            async with metrics.track(backend="dau", op="record_active"):
                await self._client.zadd(...)

        Поведение:

        * Меряем `time.perf_counter()` между `__aenter__` и `__aexit__`.
        * В `finally`-блоке инкрементируем counter
          (`outcome="ok"` при нормальном выходе / `"error"` при любом
          исключении) и observe-им histogram.
        * Если внутри блока вылетит исключение — outcome=`"error"`,
          counter инкрементнется, histogram наблюдает реальное elapsed,
          исключение re-raise-ится (контекст-менеджер не глотает).
        """
        outcome = "ok"
        start = perf_counter()
        try:
            yield
        except BaseException:
            outcome = "error"
            raise
        finally:
            elapsed = perf_counter() - start
            self._counter.labels(backend=backend, op=op, outcome=outcome).inc()
            self._histogram.labels(backend=backend, op=op).observe(elapsed)
