"""Observability-инфраструктура (Спринт 4.1-J, шаги J.1-J.2).

Модуль агрегирует Prometheus-метрики Redis-операций
(`RedisMetrics` — J.1) и фабрику HTTP-приложения `/metrics`
(`build_metrics_app` — J.2).

Архитектурно живёт в `infrastructure/` (рядом с `redis/`, `db/` и
другими адаптерами): сами метрики — реализация cross-cutting-порта
«счётчик/гистограмма», `domain` про observability не знает.
"""

from pipirik_wars.infrastructure.observability.http import build_metrics_app
from pipirik_wars.infrastructure.observability.redis_metrics import RedisMetrics

__all__ = ["RedisMetrics", "build_metrics_app"]
