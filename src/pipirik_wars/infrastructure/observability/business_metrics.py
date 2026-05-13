"""Prometheus-адаптер для `IBusinessMetrics` (Спринт 4.1-N, шаг N.1).

Конкретная реализация порта `IBusinessMetrics` поверх
`prometheus_client.Counter`/`Gauge`. Регистрируется в общий
`CollectorRegistry`, что и `RedisMetrics` (см. композицию в
`bot/main.py::build_container`).

Архитектурно отделено от `RedisMetrics` (4.1-J): тот трекает Redis-IO,
а этот — бизнес-state-changes. Однако оба используют ОДИН `/metrics`-
endpoint и один `CollectorRegistry`.

Counter-ы (накапливающиеся, `_total`-суффикс):

* `pipirik_caravan_outcomes_total{outcome}` — финализированные караваны
  per outcome.
* `pipirik_raid_outcomes_total{outcome}` — финализированные рейды.
* `pipirik_roulette_spins_total{kind, prize_class}` — спины рулетки
  per kind (free/paid) × prize_class (cm/length_bonus/...).
* `pipirik_duel_resolved_total{outcome}` — финализированные дуэли.
* `pipirik_forest_run_started_total` — стартанутые лесные забеги.
* `pipirik_forest_run_finished_total{outcome}` — финализированные.

Gauge-и (точечное значение):

* `pipirik_dau_active_users` — DAU snapshot (обновляется polling-таском).
* `pipirik_caravan_active` — текущее количество активных караванов.
* `pipirik_raid_active` — текущее количество активных рейдов.
* `pipirik_prize_pool_balance{currency}` — текущий баланс призового
  пула в base-units (stars: int; ton: float TON; usdt: float USDT).

См. также `monitoring/grafana/dashboards/business-metrics.json` —
Grafana-дашборд, который рендерит эти метрики.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge

from pipirik_wars.application.observability import (
    BusinessMetricsCurrency,
    CaravanOutcome,
    DuelResolvedOutcome,
    ForestRunOutcome,
    IBusinessMetrics,
    RaidOutcome,
    RouletteKind,
)

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

logger = logging.getLogger(__name__)


class PrometheusBusinessMetrics(IBusinessMetrics):
    """Реализация `IBusinessMetrics` поверх `prometheus_client`.

    Конструктор принимает optional `registry`:
    * `None` (default) — регистрируем в глобальный `REGISTRY`. В production
      это норма.
    * `CollectorRegistry()` — изолированный реестр (тесты, multi-instance).
      Используется в `bot/main.py::build_container` совместно с
      `RedisMetrics(registry=...)`, чтобы оба класса попадали в один
      `/metrics`-endpoint.

    Все методы — no-throw: при любой ошибке Prometheus-операции (например,
    label-cardinality-explosion) пишем `logger.warning` и продолжаем
    работу. Observability не должна ломать business-flow.
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self._dau_active_users = Gauge(
            "pipirik_dau_active_users",
            "Current Daily Active Users count (snapshot from IDauCounter)",
            registry=registry,
        )
        self._caravan_active = Gauge(
            "pipirik_caravan_active",
            "Current number of active caravans (incremented on create, "
            "decremented on finish/cancel)",
            registry=registry,
        )
        self._caravan_outcomes = Counter(
            "pipirik_caravan_outcomes_total",
            "Total caravan battles by outcome",
            labelnames=("outcome",),
            registry=registry,
        )
        self._raid_active = Gauge(
            "pipirik_raid_active",
            "Current number of active raids (incremented on summon, decremented on finish/cancel)",
            registry=registry,
        )
        self._raid_outcomes = Counter(
            "pipirik_raid_outcomes_total",
            "Total raid battles by outcome",
            labelnames=("outcome",),
            registry=registry,
        )
        self._prize_pool_balance = Gauge(
            "pipirik_prize_pool_balance",
            "Current prize pool balance in base units (stars int, ton float, usdt float)",
            labelnames=("currency",),
            registry=registry,
        )
        self._roulette_spins = Counter(
            "pipirik_roulette_spins_total",
            "Total roulette spins by kind and prize class",
            labelnames=("kind", "prize_class"),
            registry=registry,
        )
        self._duel_resolved = Counter(
            "pipirik_duel_resolved_total",
            "Total resolved duels by outcome",
            labelnames=("outcome",),
            registry=registry,
        )
        self._forest_started = Counter(
            "pipirik_forest_run_started_total",
            "Total forest runs started",
            registry=registry,
        )
        self._forest_finished = Counter(
            "pipirik_forest_run_finished_total",
            "Total forest runs finished by outcome",
            labelnames=("outcome",),
            registry=registry,
        )

    def set_dau(self, value: int) -> None:
        try:
            self._dau_active_users.set(value)
        except Exception:
            logger.warning("set_dau failed (value=%s)", value, exc_info=True)

    def inc_caravan_active(self) -> None:
        try:
            self._caravan_active.inc()
        except Exception:
            logger.warning("inc_caravan_active failed", exc_info=True)

    def dec_caravan_active(self) -> None:
        try:
            self._caravan_active.dec()
        except Exception:
            logger.warning("dec_caravan_active failed", exc_info=True)

    def inc_caravan_outcome(self, outcome: CaravanOutcome) -> None:
        try:
            self._caravan_outcomes.labels(outcome=outcome).inc()
        except Exception:
            logger.warning("inc_caravan_outcome failed (outcome=%s)", outcome, exc_info=True)

    def inc_raid_active(self) -> None:
        try:
            self._raid_active.inc()
        except Exception:
            logger.warning("inc_raid_active failed", exc_info=True)

    def dec_raid_active(self) -> None:
        try:
            self._raid_active.dec()
        except Exception:
            logger.warning("dec_raid_active failed", exc_info=True)

    def inc_raid_outcome(self, outcome: RaidOutcome) -> None:
        try:
            self._raid_outcomes.labels(outcome=outcome).inc()
        except Exception:
            logger.warning("inc_raid_outcome failed (outcome=%s)", outcome, exc_info=True)

    def set_prize_pool_balance(self, currency: BusinessMetricsCurrency, amount: float) -> None:
        try:
            self._prize_pool_balance.labels(currency=currency).set(amount)
        except Exception:
            logger.warning(
                "set_prize_pool_balance failed (currency=%s, amount=%s)",
                currency,
                amount,
                exc_info=True,
            )

    def inc_roulette_spin(self, kind: RouletteKind, prize_class: str) -> None:
        try:
            self._roulette_spins.labels(kind=kind, prize_class=prize_class).inc()
        except Exception:
            logger.warning(
                "inc_roulette_spin failed (kind=%s, prize_class=%s)",
                kind,
                prize_class,
                exc_info=True,
            )

    def inc_duel_resolved(self, outcome: DuelResolvedOutcome) -> None:
        try:
            self._duel_resolved.labels(outcome=outcome).inc()
        except Exception:
            logger.warning("inc_duel_resolved failed (outcome=%s)", outcome, exc_info=True)

    def inc_forest_started(self) -> None:
        try:
            self._forest_started.inc()
        except Exception:
            logger.warning("inc_forest_started failed", exc_info=True)

    def inc_forest_finished(self, outcome: ForestRunOutcome) -> None:
        try:
            self._forest_finished.labels(outcome=outcome).inc()
        except Exception:
            logger.warning("inc_forest_finished failed (outcome=%s)", outcome, exc_info=True)
