"""Observability-инфраструктура.

* Спринт 4.1-J — `RedisMetrics` (Prometheus-метрики Redis-операций) +
  `build_metrics_app` (фабрика HTTP `/metrics`-endpoint-а).
* Спринт 4.1-N — `PrometheusBusinessMetrics` (бизнес-метрики DAU /
  caravans / raids / prize pool / roulette / duels / forest);
  реализация порта `IBusinessMetrics` из `application/observability/`.

Архитектурно живёт в `infrastructure/` (рядом с `redis/`, `db/` и
другими адаптерами): сами метрики — реализация cross-cutting-портов,
`domain` про observability не знает.
"""

from pipirik_wars.infrastructure.observability.business_metrics import (
    PrometheusBusinessMetrics,
)
from pipirik_wars.infrastructure.observability.http import build_metrics_app
from pipirik_wars.infrastructure.observability.redis_metrics import RedisMetrics

__all__ = ["PrometheusBusinessMetrics", "RedisMetrics", "build_metrics_app"]
