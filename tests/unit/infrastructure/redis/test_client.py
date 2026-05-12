"""Unit-тесты ``build_redis_client`` (Спринт 4.1-G, шаг G.2).

Покрытие:

* Возвращает `redis.asyncio.Redis`-инстанс с `ConnectionPool`-ом.
* Параметры из ``RedisSettings`` пробрасываются в pool
  (`max_connections`, timeouts, keepalive).
* Pool-URL парсится корректно (host, port, db).

Real-network подключение НЕ устанавливается (`ConnectionPool` ленивый;
TCP-handshake откладывается до первого `await client.<cmd>()`). Тесты
закрывают клиент через `aclose()` чтобы не плодить открытые
connection-objects.
"""

from __future__ import annotations

import pytest
from redis.asyncio import ConnectionPool, Redis

from pipirik_wars.infrastructure.redis.client import build_redis_client
from pipirik_wars.infrastructure.redis.settings import RedisSettings


class TestBuildRedisClient:
    async def test_returns_redis_with_connection_pool(self) -> None:
        settings = RedisSettings()
        client = build_redis_client(settings)
        try:
            assert isinstance(client, Redis)
            assert isinstance(client.connection_pool, ConnectionPool)
        finally:
            await client.aclose()

    async def test_pool_max_connections_propagated(self) -> None:
        settings = RedisSettings(pool_max_connections=42)
        client = build_redis_client(settings)
        try:
            assert client.connection_pool.max_connections == 42
        finally:
            await client.aclose()

    async def test_pool_timeouts_propagated(self) -> None:
        settings = RedisSettings(
            connect_timeout_seconds=1.25,
            socket_timeout_seconds=2.5,
            socket_keepalive=False,
        )
        client = build_redis_client(settings)
        try:
            # ConnectionPool хранит kwargs, с которыми будут создаваться
            # Connection-объекты при первом запросе.
            kwargs = client.connection_pool.connection_kwargs
            assert kwargs["socket_connect_timeout"] == pytest.approx(1.25)
            assert kwargs["socket_timeout"] == pytest.approx(2.5)
            assert kwargs["socket_keepalive"] is False
        finally:
            await client.aclose()

    async def test_url_parsed_into_pool(self) -> None:
        settings = RedisSettings(url="redis://example.com:6380/3")
        client = build_redis_client(settings)
        try:
            kwargs = client.connection_pool.connection_kwargs
            assert kwargs["host"] == "example.com"
            assert kwargs["port"] == 6380
            assert kwargs["db"] == 3
        finally:
            await client.aclose()
