"""Smoke-тесты Grafana-дашборда `monitoring/grafana/dashboards/business-metrics.json`
(Спринт 4.1-N).

Цель этих тестов — гарантировать структурную целостность дашборда
без поднятия живого Grafana-инстанса:

1. JSON парсится как валидный JSON.
2. Top-level поля Grafana-схемы присутствуют (`schemaVersion`,
   `version`, `title`, `uid`, `panels`, `templating`).
3. Каждая data-панель (не row-разделитель) имеет хотя бы один
   PromQL-target с непустым `expr`-полем.
4. Все referenced metric-имена `pipirik_*` присутствуют в исходнике
   `PrometheusBusinessMetrics`-класса.

Эти тесты — статический guard против рассинхронизации дашборда
с источником метрик.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_DASHBOARD_PATH: Path = (
    _REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "business-metrics.json"
)
_METRICS_SOURCE_PATH: Path = (
    _REPO_ROOT / "src" / "pipirik_wars" / "infrastructure" / "observability" / "business_metrics.py"
)

_EXPECTED_METRIC_NAMES: frozenset[str] = frozenset(
    {
        "pipirik_dau_active_users",
        "pipirik_caravan_active",
        "pipirik_raid_active",
        "pipirik_prize_pool_balance",
        "pipirik_caravan_outcomes_total",
        "pipirik_raid_outcomes_total",
        "pipirik_duel_resolved_total",
        "pipirik_forest_run_started_total",
        "pipirik_forest_run_finished_total",
        "pipirik_roulette_spins_total",
    }
)


@pytest.fixture(scope="module")
def dashboard() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))
    return parsed


@pytest.fixture(scope="module")
def metrics_source() -> str:
    return _METRICS_SOURCE_PATH.read_text(encoding="utf-8")


def _iter_data_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [panel for panel in panels if panel.get("type") != "row"]


def _iter_promql_expressions(panels: list[dict[str, Any]]) -> list[str]:
    expressions: list[str] = []
    for panel in _iter_data_panels(panels):
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if expr:
                expressions.append(expr)
    return expressions


def _extract_metric_names_from_promql(expressions: list[str]) -> set[str]:
    pattern = re.compile(r"\bpipirik_[a-z_]+\b")
    found: set[str] = set()
    for expr in expressions:
        found.update(pattern.findall(expr))
    return found


def test_dashboard_path_exists() -> None:
    assert _DASHBOARD_PATH.is_file(), (
        f"Dashboard JSON not found at {_DASHBOARD_PATH}. N.4 should have created it."
    )


def test_dashboard_json_parses_as_valid_json() -> None:
    json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))


def test_dashboard_top_level_schema(dashboard: dict[str, Any]) -> None:
    for key in ("schemaVersion", "version", "title", "uid", "panels", "templating"):
        assert key in dashboard, f"Top-level key {key!r} missing in dashboard"
    assert dashboard["uid"] == "pipirik-business-ops"
    assert dashboard["schemaVersion"] >= 39
    assert dashboard["title"]


def test_dashboard_has_rows(dashboard: dict[str, Any]) -> None:
    """Дашборд должен иметь 5+ row-разделителей (по семантическим группам)."""
    rows = [panel for panel in dashboard["panels"] if panel.get("type") == "row"]
    assert len(rows) >= 5, f"Expected >=5 rows for semantic grouping, got {len(rows)}"


def test_dashboard_has_data_panels(dashboard: dict[str, Any]) -> None:
    """Должно быть >=10 data-панелей (статы + timeseries)."""
    data_panels = _iter_data_panels(dashboard["panels"])
    assert len(data_panels) >= 10, f"Expected >=10 data panels, got {len(data_panels)}"


def test_every_data_panel_has_promql_target(dashboard: dict[str, Any]) -> None:
    for panel in _iter_data_panels(dashboard["panels"]):
        targets = panel.get("targets", [])
        assert targets, f"Panel {panel.get('id')} has no targets"
        expressions = [t.get("expr") for t in targets if t.get("expr")]
        assert expressions, f"Panel {panel.get('id')} ({panel.get('title')}) has no non-empty expr"


def test_all_metric_names_exist_in_source(dashboard: dict[str, Any], metrics_source: str) -> None:
    expressions = _iter_promql_expressions(dashboard["panels"])
    used_metrics = _extract_metric_names_from_promql(expressions)
    assert used_metrics, "No pipirik_* metric names found in PromQL expressions"
    for metric in used_metrics:
        literal = f'"{metric}"'
        assert literal in metrics_source, (
            f"Metric {metric!r} used in dashboard but not declared in business_metrics.py"
        )


def test_all_expected_metrics_used_in_dashboard(dashboard: dict[str, Any]) -> None:
    expressions = _iter_promql_expressions(dashboard["panels"])
    used_metrics = _extract_metric_names_from_promql(expressions)
    missing = _EXPECTED_METRIC_NAMES - used_metrics
    assert not missing, (
        f"Metrics declared in PrometheusBusinessMetrics but not visualized: {missing}"
    )


def test_datasource_uid_is_placeholder(dashboard: dict[str, Any]) -> None:
    """Все targets ссылаются на ${DS_PROMETHEUS}, чтобы оператор подставил при импорте."""
    for panel in _iter_data_panels(dashboard["panels"]):
        for target in panel.get("targets", []):
            ds = target.get("datasource", {})
            uid = ds.get("uid")
            assert uid == "${DS_PROMETHEUS}", (
                f"Panel {panel.get('id')} target uses uid={uid!r}, expected ${{DS_PROMETHEUS}}"
            )


def test_templating_includes_ds_prometheus_variable(dashboard: dict[str, Any]) -> None:
    templating_list = dashboard.get("templating", {}).get("list", [])
    names = {var.get("name") for var in templating_list}
    assert "DS_PROMETHEUS" in names, f"DS_PROMETHEUS variable missing in templating list: {names}"
