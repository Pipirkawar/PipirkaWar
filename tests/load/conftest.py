"""Общие фикстуры/утилиты для load-тестов (Спринт 4.1-J).

В этом модуле живёт:

* ``ops_count``           — значение env-var-а ``LOAD_OPS_COUNT``
  (число операций в сценарии; по умолчанию 2000).

* ``p99_budget_ms``       — env-var ``LOAD_P99_BUDGET_MS``
  (миллисекундный таргет p99 для одной операции; по умолчанию 50 мс).

* ``measure_p99``         — утилита, считающая p99-латенси из
  ``list[float]`` (секунды) и возвращающая **миллисекунды**.

Все load-тесты помечены ``pytest.mark.load`` (см. ``pyproject.toml``).
"""

from __future__ import annotations

import math
import os

import pytest

# Дефолты по AGENT_HANDOFF.md (4.1-J J.0): 2000 ops, p99 < 50ms.
# В CI это даёт ≈30 с на полный набор; на staging-Redis-е можно
# через env поднять до 100_000+.
_DEFAULT_OPS_COUNT = 2000
_DEFAULT_P99_BUDGET_MS = 50.0


@pytest.fixture(scope="session")
def ops_count() -> int:
    """Сколько операций гонять в каждом сценарии. ``LOAD_OPS_COUNT``."""
    return int(os.environ.get("LOAD_OPS_COUNT", _DEFAULT_OPS_COUNT))


@pytest.fixture(scope="session")
def p99_budget_ms() -> float:
    """Бюджет p99-латенси одной операции в миллисекундах."""
    return float(os.environ.get("LOAD_P99_BUDGET_MS", _DEFAULT_P99_BUDGET_MS))


def measure_p99(latencies_seconds: list[float]) -> float:
    """Вернуть p99 (миллисекунды) из массива latency-измерений в секундах.

    Используется ``math.ceil``-индекс (nearest-rank percentile): для
    `N` значений p99 — это значение по индексу ``ceil(0.99 * N) - 1``
    в отсортированном массиве. Это совпадает с тем, что считают
    Prometheus-histogram-quantile и большинство APM-систем.

    Args:
        latencies_seconds: список latency-измерений в секундах
            (например, ``time.perf_counter()``-elapsed).

    Returns:
        p99-латенси в миллисекундах.

    Raises:
        ValueError: если список пуст (нечего ранжировать).
    """
    if not latencies_seconds:
        raise ValueError("latencies list must not be empty")
    sorted_latencies = sorted(latencies_seconds)
    idx = max(0, math.ceil(0.99 * len(sorted_latencies)) - 1)
    return sorted_latencies[idx] * 1000.0
