"""Cross-cutting-порты для бизнес-метрик (Спринт 4.1-N).

Прокидываются в use-case-ы как optional-зависимость с null-object-default-ом
(`NullBusinessMetrics`), чтобы тесты использовали no-op-реализацию без
необходимости настраивать Prometheus-моки на каждом тесте.

Production-сборка получает `PrometheusBusinessMetrics` из
`infrastructure.observability.business_metrics`, который инкрементирует
реальные Prometheus-метрики на общем `CollectorRegistry`-е с
`RedisMetrics` (см. композицию в `bot/main.py`).
"""

from pipirik_wars.application.observability.business_metrics import (
    BusinessMetricsCurrency,
    CaravanOutcome,
    DuelResolvedOutcome,
    ForestRunOutcome,
    IBusinessMetrics,
    NullBusinessMetrics,
    RaidOutcome,
    RouletteKind,
)

__all__ = [
    "BusinessMetricsCurrency",
    "CaravanOutcome",
    "DuelResolvedOutcome",
    "ForestRunOutcome",
    "IBusinessMetrics",
    "NullBusinessMetrics",
    "RaidOutcome",
    "RouletteKind",
]
