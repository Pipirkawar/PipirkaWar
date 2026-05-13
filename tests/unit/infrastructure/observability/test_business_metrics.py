"""Unit-тесты `PrometheusBusinessMetrics` (Спринт 4.1-N).

Покрытие 10 метрик из `application.observability.IBusinessMetrics`-порта:

* Gauge `pipirik_dau_active_users` — `set_dau(value)`
* Gauge `pipirik_caravan_active` — `inc_caravan_active()` / `dec_caravan_active()`
* Gauge `pipirik_raid_active` — `inc_raid_active()` / `dec_raid_active()`
* Gauge `pipirik_prize_pool_balance{currency}` — `set_prize_pool_balance(currency, amount)`
* Counter `pipirik_caravan_outcomes_total{outcome}` — `inc_caravan_outcome(outcome)`
* Counter `pipirik_raid_outcomes_total{outcome}` — `inc_raid_outcome(outcome)`
* Counter `pipirik_duel_resolved_total{outcome}` — `inc_duel_resolved(outcome)`
* Counter `pipirik_forest_run_started_total` — `inc_forest_started()`
* Counter `pipirik_forest_run_finished_total{outcome}` — `inc_forest_finished(outcome)`
* Counter `pipirik_roulette_spins_total{kind, prize_class}` — `inc_roulette_spin(kind, prize_class)`

Изоляция: на каждый тест свежий `CollectorRegistry`, иначе
`prometheus_client` падает «Duplicated timeseries» (Counter/Gauge
регистрируются глобально).
"""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from pipirik_wars.application.observability import NullBusinessMetrics
from pipirik_wars.infrastructure.observability.business_metrics import (
    PrometheusBusinessMetrics,
)


@pytest.fixture
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def metrics(registry: CollectorRegistry) -> PrometheusBusinessMetrics:
    return PrometheusBusinessMetrics(registry=registry)


def _gauge_value(
    registry: CollectorRegistry,
    name: str,
    labels: dict[str, str] | None = None,
) -> float:
    return registry.get_sample_value(name, labels or {}) or 0.0


def _counter_value(
    registry: CollectorRegistry,
    name: str,
    labels: dict[str, str] | None = None,
) -> float:
    return registry.get_sample_value(f"{name}_total", labels or {}) or 0.0


class TestDauGauge:
    def test_set_dau_writes_to_gauge(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.set_dau(42)
        assert _gauge_value(registry, "pipirik_dau_active_users") == 42.0

    def test_set_dau_overwrites_previous(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.set_dau(100)
        metrics.set_dau(73)
        assert _gauge_value(registry, "pipirik_dau_active_users") == 73.0


class TestCaravanGaugeAndCounter:
    def test_inc_dec_caravan_active(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.inc_caravan_active()
        metrics.inc_caravan_active()
        metrics.inc_caravan_active()
        metrics.dec_caravan_active()
        assert _gauge_value(registry, "pipirik_caravan_active") == 2.0

    @pytest.mark.parametrize(
        "outcome",
        ["raiders_win", "owner_win", "draw", "cancelled"],
    )
    def test_inc_caravan_outcome(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        outcome: str,
    ) -> None:
        metrics.inc_caravan_outcome(outcome)  # type: ignore[arg-type]
        assert _counter_value(registry, "pipirik_caravan_outcomes", {"outcome": outcome}) == 1.0


class TestRaidGaugeAndCounter:
    def test_inc_dec_raid_active(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.inc_raid_active()
        metrics.inc_raid_active()
        metrics.dec_raid_active()
        assert _gauge_value(registry, "pipirik_raid_active") == 1.0

    @pytest.mark.parametrize(
        "outcome",
        ["raiders_win", "boss_win", "cancelled"],
    )
    def test_inc_raid_outcome(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        outcome: str,
    ) -> None:
        metrics.inc_raid_outcome(outcome)  # type: ignore[arg-type]
        assert _counter_value(registry, "pipirik_raid_outcomes", {"outcome": outcome}) == 1.0


class TestPrizePoolGauge:
    @pytest.mark.parametrize(
        ("currency", "amount"),
        [("stars", 12345.0), ("ton", 1_500_000_000.0), ("usdt", 2_000_000.0)],
    )
    def test_set_prize_pool_balance(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        currency: str,
        amount: float,
    ) -> None:
        metrics.set_prize_pool_balance(currency, amount)  # type: ignore[arg-type]
        assert (
            _gauge_value(registry, "pipirik_prize_pool_balance", {"currency": currency}) == amount
        )

    def test_set_prize_pool_balance_overwrites(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.set_prize_pool_balance("stars", 100.0)
        metrics.set_prize_pool_balance("stars", 75.0)
        assert _gauge_value(registry, "pipirik_prize_pool_balance", {"currency": "stars"}) == 75.0


class TestDuelCounter:
    @pytest.mark.parametrize(
        "outcome",
        ["p1_win", "p2_win", "draw", "p1_afk", "p2_afk"],
    )
    def test_inc_duel_resolved(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        outcome: str,
    ) -> None:
        metrics.inc_duel_resolved(outcome)  # type: ignore[arg-type]
        assert _counter_value(registry, "pipirik_duel_resolved", {"outcome": outcome}) == 1.0


class TestForestCounters:
    def test_inc_forest_started(
        self, metrics: PrometheusBusinessMetrics, registry: CollectorRegistry
    ) -> None:
        metrics.inc_forest_started()
        metrics.inc_forest_started()
        assert _counter_value(registry, "pipirik_forest_run_started") == 2.0

    @pytest.mark.parametrize(
        "outcome",
        ["success", "drop", "idle_timeout", "cancelled"],
    )
    def test_inc_forest_finished(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        outcome: str,
    ) -> None:
        metrics.inc_forest_finished(outcome)  # type: ignore[arg-type]
        assert _counter_value(registry, "pipirik_forest_run_finished", {"outcome": outcome}) == 1.0


class TestRouletteCounter:
    @pytest.mark.parametrize(
        ("kind", "prize_class"),
        [("free", "common"), ("paid", "rare"), ("paid", "legendary")],
    )
    def test_inc_roulette_spin(
        self,
        metrics: PrometheusBusinessMetrics,
        registry: CollectorRegistry,
        kind: str,
        prize_class: str,
    ) -> None:
        metrics.inc_roulette_spin(kind, prize_class)  # type: ignore[arg-type]
        assert (
            _counter_value(
                registry,
                "pipirik_roulette_spins",
                {"kind": kind, "prize_class": prize_class},
            )
            == 1.0
        )


class TestNullBusinessMetrics:
    """Null-object — все методы no-op, не должны бросать исключения."""

    def test_all_methods_are_noop(self) -> None:
        m = NullBusinessMetrics()
        m.set_dau(0)
        m.set_dau(123)
        m.inc_caravan_active()
        m.dec_caravan_active()
        m.inc_caravan_outcome("raiders_win")
        m.inc_raid_active()
        m.dec_raid_active()
        m.inc_raid_outcome("boss_win")
        m.set_prize_pool_balance("stars", 0.0)
        m.inc_roulette_spin("free", "common")
        m.inc_duel_resolved("p1_win")
        m.inc_forest_started()
        m.inc_forest_finished("success")
