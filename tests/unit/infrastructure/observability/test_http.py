"""Unit-тесты `build_metrics_app` (Спринт 4.1-J, шаг J.2).

Покрытие:

* GET `/metrics` → 200 OK + Content-Type
  ``prometheus_client.CONTENT_TYPE_LATEST`` (на 0.25.x:
  ``text/plain; version=1.0.0; charset=utf-8``).
* Тело ответа содержит имена обоих метрик из `RedisMetrics`
  (`pipirik_redis_op_total` и `pipirik_redis_op_duration_seconds`),
  если в переданном `registry`-е они зарегистрированы и хотя бы раз
  получили observation.
* Любой другой path → 404 Not Found (default aiohttp-router).
* Любой другой метод (POST/PUT/DELETE) на `/metrics` → 405 Method Not
  Allowed (default aiohttp-router).
* Пустой `registry` (без зарегистрированных метрик) → 200 OK с пустым
  телом, что не падает (sanity-edge-case).

Тесты используют `aiohttp.test_utils.TestServer` + `TestClient` —
встроенный test-harness aiohttp-а, не требует `pytest-aiohttp`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry

from pipirik_wars.infrastructure.observability.http import build_metrics_app
from pipirik_wars.infrastructure.observability.redis_metrics import RedisMetrics


@pytest_asyncio.fixture
async def registry_with_observations() -> CollectorRegistry:
    """`CollectorRegistry` с предзаполненными observation-ами по обоим метрикам."""
    registry = CollectorRegistry()
    metrics = RedisMetrics(registry=registry)
    async with metrics.track(backend="dau", op="record_active"):
        pass
    return registry


@pytest_asyncio.fixture
async def metrics_client(
    registry_with_observations: CollectorRegistry,
) -> AsyncIterator[TestClient[web.Request, web.Application]]:
    """`TestClient` для `aiohttp.web.Application` с эндпоинтом `/metrics`."""
    app = build_metrics_app(registry_with_observations)
    server = TestServer(app)
    client: TestClient[web.Request, web.Application] = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


class TestMetricsEndpoint:
    async def test_get_metrics_returns_200_with_prometheus_content_type(
        self,
        metrics_client: TestClient[web.Request, web.Application],
    ) -> None:
        """GET /metrics → 200 OK + правильный Content-Type."""
        response = await metrics_client.get("/metrics")
        assert response.status == 200
        # `prometheus_client.CONTENT_TYPE_LATEST` — точный заголовок, ожидаемый
        # Prometheus-scrape-ером (включая `version=X.Y.Z` параметр и charset).
        assert response.headers["Content-Type"] == CONTENT_TYPE_LATEST

    async def test_get_metrics_body_contains_metric_names(
        self,
        metrics_client: TestClient[web.Request, web.Application],
    ) -> None:
        """Payload содержит имена обеих метрик из `RedisMetrics`."""
        response = await metrics_client.get("/metrics")
        body = await response.text()
        # Counter `pipirik_redis_op_total` появляется в HELP-/TYPE-/sample-строках.
        assert "pipirik_redis_op_total" in body
        # Histogram — три серии (_bucket, _count, _sum) + HELP/TYPE; имя
        # `pipirik_redis_op_duration_seconds` встречается как минимум 3 раза.
        assert "pipirik_redis_op_duration_seconds" in body

    async def test_get_metrics_body_contains_sample_value(
        self,
        metrics_client: TestClient[web.Request, web.Application],
    ) -> None:
        """Конкретное наблюдение (success-counter после track) попадает в payload."""
        response = await metrics_client.get("/metrics")
        body = await response.text()
        # `metrics.track(backend="dau", op="record_active")` без исключения →
        # counter `pipirik_redis_op_total{backend="dau",op="record_active",outcome="ok"} 1.0`.
        assert 'backend="dau"' in body
        assert 'op="record_active"' in body
        assert 'outcome="ok"' in body

    async def test_unknown_path_returns_404(
        self,
        metrics_client: TestClient[web.Request, web.Application],
    ) -> None:
        """Любой другой path (не `/metrics`) → 404 Not Found."""
        response = await metrics_client.get("/health")
        assert response.status == 404
        response = await metrics_client.get("/")
        assert response.status == 404

    async def test_post_to_metrics_returns_405(
        self,
        metrics_client: TestClient[web.Request, web.Application],
    ) -> None:
        """POST/PUT/DELETE на `/metrics` → 405 Method Not Allowed."""
        response = await metrics_client.post("/metrics", data=b"ignored")
        assert response.status == 405


class TestMetricsEndpointEmptyRegistry:
    """Sanity: пустой `CollectorRegistry` без зарегистрированных метрик."""

    async def test_empty_registry_returns_200(self) -> None:
        """Без observation-ов endpoint всё равно отвечает 200 OK."""
        registry = CollectorRegistry()
        app = build_metrics_app(registry)
        server = TestServer(app)
        client: TestClient[web.Request, web.Application] = TestClient(server)
        await client.start_server()
        try:
            response = await client.get("/metrics")
            assert response.status == 200
            assert response.headers["Content-Type"] == CONTENT_TYPE_LATEST
            body = await response.text()
            # `generate_latest()` с пустым registry возвращает пустую строку.
            assert body == ""
        finally:
            await client.close()
