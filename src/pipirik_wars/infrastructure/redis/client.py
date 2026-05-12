"""Фабрика `redis.asyncio.Redis` (Спринт 4.1-G, шаг G.2).

`build_redis_client(settings) -> Redis` создаёт long-lived async-Redis-
клиент с явным `ConnectionPool`-ом по параметрам `RedisSettings`.
Композиционный root (`bot/main.py`) вызывает фабрику ровно один раз
и переиспользует singleton для всех Redis-репозиториев — это
best-practice для `redis-py >= 5.0` (создание Redis на каждый вызов
плодит TCP-соединения и убивает throughput).

Graceful-shutdown в bot-е — `await client.aclose()` (см. 4.1-G G.4 — на
данный момент leak небольшой, отдельный shutdown-hook не добавляется).
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from pipirik_wars.infrastructure.redis.settings import RedisSettings

__all__ = ["build_redis_client"]


def build_redis_client(settings: RedisSettings) -> Redis:
    """Создать `redis.asyncio.Redis` с явным `ConnectionPool`-ом.

    Параметры пула берутся из ``settings``. Возвращаемый клиент —
    long-lived singleton; вызывай ровно один раз в composition root-е
    и переиспользуй для всех Redis-репозиториев.

    Note: `Redis.from_url(...)` создал бы pool неявно, но мы выбираем
    явный `ConnectionPool.from_url(...)` чтобы:

    1. Все pool-параметры были явно зафиксированы в одном месте.
    2. В будущем (4.1-J / load-test) проще будет наблюдать pool-метрики
       через `connection_pool.connection_kwargs` / `.max_connections`.
    3. Тесты могут подменить `ConnectionPool`-фабрику если нужно
       (без monkey-patch-а `Redis.from_url`).
    """
    pool = ConnectionPool.from_url(
        settings.url,
        max_connections=settings.pool_max_connections,
        socket_connect_timeout=settings.connect_timeout_seconds,
        socket_timeout=settings.socket_timeout_seconds,
        socket_keepalive=settings.socket_keepalive,
    )
    return Redis(connection_pool=pool)
