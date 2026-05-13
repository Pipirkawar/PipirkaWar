"""Smoke-тесты Grafana-дашборда `monitoring/grafana/dashboards/redis-metrics.json`
(Спринт 4.1-L).

Цель этих тестов — гарантировать структурную целостность дашборда
без поднятия живого Grafana-инстанса:

1. JSON парсится как валидный JSON.
2. Top-level поля Grafana-схемы присутствуют (`schemaVersion`,
   `version`, `title`, `uid`, `panels`, `templating`).
3. Каждая data-панель (не row-разделитель) имеет хотя бы один
   PromQL-target с непустым `expr`-полем.
4. Все referenced metric-имена (`pipirik_redis_op_total`,
   `pipirik_redis_op_duration_seconds`, ...`_bucket`-derivatives)
   присутствуют в исходнике `RedisMetrics`-класса.
5. Все referenced label-имена (`backend`, `op`, `outcome`)
   объявлены в `labelnames`-кортежах `RedisMetrics.__init__`.
6. Все backend-значения, использованные в шаблоне переменных
   и фильтрах (`activity_lock` / `lobby` / `dau`), совпадают с
   `_BACKEND`-константами в соответствующих репозиториях.

Эти тесты — статический guard против рассинхронизации дашборда
с источником метрик. Если кто-то переименует backend-label или
удалит/переименует одну из метрик в `redis_metrics.py`, тест
упадёт до merge-а.

Тесты лежат в `tests/integration/` (а не `tests/unit/`), потому
что читают файлы с диска (dashboard JSON + исходник метрик).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_DASHBOARD_PATH: Path = _REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "redis-metrics.json"
_METRICS_SOURCE_PATH: Path = (
    _REPO_ROOT / "src" / "pipirik_wars" / "infrastructure" / "observability" / "redis_metrics.py"
)
_REDIS_REPOS_DIR: Path = (
    _REPO_ROOT / "src" / "pipirik_wars" / "infrastructure" / "redis" / "repositories"
)

# Имена метрик, объявленные в `RedisMetrics.__init__` через
# `Counter(...)` / `Histogram(...)`. Производные метрики
# Prometheus (`_bucket` / `_count` / `_sum`) генерируются автоматически
# из histogram-имени, поэтому в тесте на присутствие проверяем
# базовое имя и игнорируем суффиксы.
_EXPECTED_METRIC_BASENAMES: frozenset[str] = frozenset(
    {
        "pipirik_redis_op_total",
        "pipirik_redis_op_duration_seconds",
    }
)
_HISTOGRAM_SUFFIXES: frozenset[str] = frozenset({"_bucket", "_count", "_sum"})

_EXPECTED_LABEL_NAMES: frozenset[str] = frozenset({"backend", "op", "outcome"})

_EXPECTED_BACKEND_VALUES: frozenset[str] = frozenset({"activity_lock", "lobby", "dau"})


@pytest.fixture(scope="module")
def dashboard() -> dict[str, Any]:
    """Распарсенный JSON дашборда. Один раз на модуль."""
    parsed: dict[str, Any] = json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))
    return parsed


@pytest.fixture(scope="module")
def metrics_source() -> str:
    """Исходник `redis_metrics.py` целиком — для regex-проверок."""
    return _METRICS_SOURCE_PATH.read_text(encoding="utf-8")


def _iter_data_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Отфильтровать row-разделители — они не имеют targets."""
    return [panel for panel in panels if panel.get("type") != "row"]


def _iter_promql_expressions(panels: list[dict[str, Any]]) -> list[str]:
    """Собрать все PromQL-`expr`-строки со всех data-панелей."""
    expressions: list[str] = []
    for panel in _iter_data_panels(panels):
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if expr:
                expressions.append(expr)
    return expressions


def _extract_metric_names_from_promql(expressions: list[str]) -> set[str]:
    """Извлечь имена метрик (`pipirik_*`) из PromQL-выражений.

    Регексп ловит идентификаторы, начинающиеся с `pipirik_` и
    состоящие из снейк-кейса. Это аппроксимация — но достаточная,
    потому что других идентификаторов с префиксом `pipirik_` в
    наших дашбордах нет.
    """
    pattern = re.compile(r"\bpipirik_[a-z_]+\b")
    found: set[str] = set()
    for expr in expressions:
        found.update(pattern.findall(expr))
    return found


def _normalize_metric_name(name: str) -> str:
    """Снять histogram-суффиксы (`_bucket`/`_count`/`_sum`) с имени.

    Prometheus-histogram автогенерирует три производные метрики
    из одного `Histogram(name=...)`. В источнике объявлено
    `pipirik_redis_op_duration_seconds`, в дашборде используется
    `pipirik_redis_op_duration_seconds_bucket` — обе строки
    нормализуются к базовому имени для сверки.
    """
    for suffix in _HISTOGRAM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def test_dashboard_path_exists() -> None:
    """Файл с дашбордом физически присутствует в репозитории."""
    assert _DASHBOARD_PATH.is_file(), (
        f"Dashboard JSON not found at {_DASHBOARD_PATH}. L.1 коммит 4.1-L должен был его создать."
    )


def test_dashboard_json_parses_as_valid_json() -> None:
    """JSON парсится без исключений `json.JSONDecodeError`."""
    # Если файл невалидный — `json.loads` выбросит исключение, тест упадёт.
    data = json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "Top-level dashboard JSON должен быть объектом."


def test_dashboard_has_required_top_level_fields(
    dashboard: dict[str, Any],
) -> None:
    """Top-level схема Grafana-дашборда (schemaVersion ≥ 30 + uid и т.д.)."""
    required_fields = {
        "schemaVersion",
        "version",
        "title",
        "uid",
        "panels",
        "templating",
        "time",
        "tags",
    }
    missing = required_fields - dashboard.keys()
    assert not missing, f"Dashboard JSON missing fields: {sorted(missing)}"

    # schemaVersion должна соответствовать Grafana 11.x (≥ 39).
    assert dashboard["schemaVersion"] >= 30, (
        f"schemaVersion={dashboard['schemaVersion']}, ожидалось ≥30 (Grafana 9+)."
    )

    # `panels` — список (даже пустой допустим в принципе, но у нас 11).
    assert isinstance(dashboard["panels"], list)
    assert dashboard["panels"], "Dashboard должен содержать хотя бы одну панель."


def test_each_data_panel_has_promql_targets(dashboard: dict[str, Any]) -> None:
    """Каждая non-row-панель имеет хотя бы один target с непустым `expr`."""
    data_panels = _iter_data_panels(dashboard["panels"])
    assert data_panels, "Ожидалась хотя бы одна data-панель (не row)."

    for panel in data_panels:
        title = panel.get("title", "<no title>")
        targets = panel.get("targets")
        assert targets, f"Panel {title!r} без targets[]."
        first_target = targets[0]
        expr = first_target.get("expr")
        assert isinstance(expr, str) and expr.strip(), (
            f"Panel {title!r}: первый target должен иметь непустой `expr`-строку."
        )


def test_referenced_metric_names_exist_in_source(
    dashboard: dict[str, Any],
    metrics_source: str,
) -> None:
    """Все `pipirik_*`-имена из PromQL-выражений объявлены в `redis_metrics.py`.

    Производные имена с суффиксами `_bucket`/`_count`/`_sum` сводятся
    к базовому имени histogram-а.
    """
    expressions = _iter_promql_expressions(dashboard["panels"])
    assert expressions, "Не найдено ни одного PromQL-выражения в дашборде."

    referenced = _extract_metric_names_from_promql(expressions)
    assert referenced, "Не найдено ни одного `pipirik_*`-имени в PromQL-выражениях."

    normalized = {_normalize_metric_name(name) for name in referenced}
    unknown = normalized - _EXPECTED_METRIC_BASENAMES
    assert not unknown, (
        f"Дашборд ссылается на неизвестные метрики (после нормализации): "
        f"{sorted(unknown)}. Ожидались: {sorted(_EXPECTED_METRIC_BASENAMES)}."
    )

    # И обратное: каждая базовая метрика, объявленная в коде, должна
    # быть использована в дашборде (иначе зачем мы её собираем).
    for metric in _EXPECTED_METRIC_BASENAMES:
        assert metric in metrics_source, (
            f"Метрика {metric!r} ожидалась в {_METRICS_SOURCE_PATH}, но не найдена в исходнике."
        )
        assert metric in normalized, (
            f"Метрика {metric!r} объявлена в коде, но не используется ни в одной панели дашборда."
        )


def test_metric_labels_match_source(metrics_source: str) -> None:
    """`labelnames=(...)`-кортежи в `RedisMetrics.__init__` содержат
    те же метки, которые мы используем в селекторах дашборда."""
    # Counter labelnames: backend, op, outcome.
    counter_match = re.search(
        r'Counter\(\s*"pipirik_redis_op_total"[^)]*labelnames=\(([^)]+)\)',
        metrics_source,
        re.DOTALL,
    )
    assert counter_match, "Не нашёл объявление Counter(`pipirik_redis_op_total`)."
    counter_labels = {
        label.strip().strip('"').strip("'")
        for label in counter_match.group(1).split(",")
        if label.strip()
    }
    assert counter_labels == _EXPECTED_LABEL_NAMES, (
        f"Counter labels: ожидались {sorted(_EXPECTED_LABEL_NAMES)}, "
        f"в коде {sorted(counter_labels)}."
    )

    # Histogram labelnames: backend, op (без outcome — длительность
    # фиксируется одинаково для ok/error, разделение по outcome
    # делается на counter-е).
    histogram_match = re.search(
        r'Histogram\(\s*"pipirik_redis_op_duration_seconds"[^)]*'
        r"labelnames=\(([^)]+)\)",
        metrics_source,
        re.DOTALL,
    )
    assert histogram_match, "Не нашёл объявление Histogram(`..._duration_seconds`)."
    histogram_labels = {
        label.strip().strip('"').strip("'")
        for label in histogram_match.group(1).split(",")
        if label.strip()
    }
    assert histogram_labels == {"backend", "op"}, (
        f"Histogram labels: ожидались {{backend, op}}, в коде {sorted(histogram_labels)}."
    )


def test_backend_values_match_repository_constants() -> None:
    """`_BACKEND`-константы в трёх Redis-репозиториях совпадают с
    ожидаемым множеством `{activity_lock, lobby, dau}`."""
    found: dict[Path, str] = {}
    for repo_file in _REDIS_REPOS_DIR.glob("*.py"):
        if repo_file.name == "__init__.py":
            continue
        text = repo_file.read_text(encoding="utf-8")
        match = re.search(r'_BACKEND\s*=\s*"([^"]+)"', text)
        if match:
            found[repo_file] = match.group(1)

    assert found, f'Не нашёл ни одного `_BACKEND = "..."` в {_REDIS_REPOS_DIR}.'

    backend_values = set(found.values())
    assert backend_values == _EXPECTED_BACKEND_VALUES, (
        f"_BACKEND-константы: в коде {sorted(backend_values)}, "
        f"ожидались {sorted(_EXPECTED_BACKEND_VALUES)}. "
        f"Найдено в файлах: { {p.name: v for p, v in found.items()} }"
    )


def test_template_variables_declared(dashboard: dict[str, Any]) -> None:
    """В templating-секции присутствуют переменные `DS_PROMETHEUS`
    (datasource-picker) и `backend` (multi-select)."""
    variables = {v["name"] for v in dashboard["templating"]["list"]}
    assert "DS_PROMETHEUS" in variables, (
        "Шаблонная переменная `DS_PROMETHEUS` ожидалась в templating-секции."
    )
    assert "backend" in variables, (
        "Шаблонная переменная `backend` ожидалась в templating-секции "
        "(нужна для фильтрации панелей по backend-у)."
    )

    backend_var = next(v for v in dashboard["templating"]["list"] if v["name"] == "backend")
    assert backend_var["type"] == "query", (
        f"Переменная `backend` должна быть типа `query`, а не {backend_var['type']!r}."
    )
    assert "label_values(pipirik_redis_op_total, backend)" in str(backend_var.get("query", "")), (
        "Переменная `backend` должна резолвиться через `label_values(...)`."
    )


def test_dashboard_uid_and_title() -> None:
    """`uid` стабилен и `title` совпадает с README + history.md."""
    dashboard = json.loads(_DASHBOARD_PATH.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "pipirik-redis-ops", (
        f"Dashboard UID = {dashboard['uid']!r}, ожидалось 'pipirik-redis-ops'."
    )
    assert dashboard["title"] == "Pipirik Redis Operations", (
        f"Dashboard title = {dashboard['title']!r}, ожидалось 'Pipirik Redis Operations'."
    )
