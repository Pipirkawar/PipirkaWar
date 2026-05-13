"""HTTP-endpoint `/metrics` для Prometheus-scrape-ера (Спринт 4.1-J, шаг J.2).

`build_metrics_app(registry) -> aiohttp.web.Application` создаёт
`aiohttp.web.Application` с одним GET-route-ом ``/metrics``, который
отдаёт snapshot всех метрик из переданного `CollectorRegistry`-а в
текстовом Prometheus-формате (`prometheus_client.generate_latest`).
Content-Type — `prometheus_client.CONTENT_TYPE_LATEST`
(на `prometheus_client==0.25.x` — ``text/plain; version=1.0.0;
charset=utf-8``, на старых версиях — ``text/plain; version=0.0.4;
charset=utf-8``; формат wire-compatible, используем константу
библиотеки, чтобы не зашивать конкретную версию).

Любой другой путь / метод → стандартный aiohttp 404 / 405 (отдельно
не обрабатываем — Prometheus-scrape-ер по контракту ходит только в
GET ``/metrics``; кастомные 404-страницы для observability-endpoint-а
не нужны).

Порт указывается отдельно от Telegram-long-polling-а:
`BOT_METRICS_PORT` (default `9100`), см.
`BotSettings.metrics_port`. В composition-root-е (`bot/main.py`)
запуск web-runner-а — **только** при `needs_redis=True`: Prometheus-
метрики Redis-операций бессмысленны при default-sql-конфигурации.

Почему отдельный port, а не path на основном bot-сервере: у
aiogram-poll-bot-а **нет** HTTP-сервера в принципе (он сам исходящий
клиент Telegram-API); поднимать его специально под `/metrics`-роут
сложнее, чем поднять lightweight aiohttp-app на отдельном порту.
9100 — конвенциональный Prometheus-node-exporter-порт, его легко
сконфигурить в `prometheus.yml`-scrape-конфиге.
"""

from __future__ import annotations

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

__all__ = ["build_metrics_app"]


_METRICS_PATH = "/metrics"


def build_metrics_app(registry: CollectorRegistry) -> web.Application:
    """Сконструировать `aiohttp.web.Application` для Prometheus-scrape-ера.

    Возвращает `aiohttp.web.Application` с единственным GET-route-ом
    ``/metrics``, который синхронно собирает snapshot переданного
    `CollectorRegistry` через ``prometheus_client.generate_latest``
    и отдаёт payload с Content-Type
    ``prometheus_client.CONTENT_TYPE_LATEST``.

    Не запускает web-runner — это ответственность вызывающего кода
    (composition-root в `bot/main.py`).
    """
    app = web.Application()

    async def _handle_metrics(_request: web.Request) -> web.Response:
        """GET /metrics → текстовый snapshot всех метрик registry."""
        payload = generate_latest(registry)
        return web.Response(
            body=payload,
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    app.router.add_get(_METRICS_PATH, _handle_metrics)
    return app
