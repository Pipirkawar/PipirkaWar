"""Unit-тесты ``RedisSettings`` (Спринт 4.1-G, шаг G.2).

Покрытие:

* Default-ы (local-dev URL, pool=20, timeouts=5s, keepalive=True).
* Explicit-конструктор перекрывает любое поле.
* Env-override через `BOT_REDIS_*` (monkeypatch).
* Field-invariants:
  - ``pool_max_connections > 0``
  - ``connect_timeout_seconds > 0``
  - ``socket_timeout_seconds > 0``
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipirik_wars.infrastructure.redis.settings import RedisSettings


class TestDefaults:
    def test_local_dev_defaults(self) -> None:
        s = RedisSettings()
        assert s.url == "redis://localhost:6379/0"
        assert s.pool_max_connections == 20
        assert s.connect_timeout_seconds == 5.0
        assert s.socket_timeout_seconds == 5.0
        assert s.socket_keepalive is True


class TestExplicitConstructor:
    def test_explicit_values_override_defaults(self) -> None:
        s = RedisSettings(
            url="rediss://redis.example.com:6380/2",
            pool_max_connections=50,
            connect_timeout_seconds=2.5,
            socket_timeout_seconds=3.0,
            socket_keepalive=False,
        )
        assert s.url == "rediss://redis.example.com:6380/2"
        assert s.pool_max_connections == 50
        assert s.connect_timeout_seconds == 2.5
        assert s.socket_timeout_seconds == 3.0
        assert s.socket_keepalive is False


class TestEnvOverride:
    def test_env_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOT_REDIS_URL", "redis://prod.example.com:6379/1")
        monkeypatch.setenv("BOT_REDIS_POOL_MAX_CONNECTIONS", "100")
        monkeypatch.setenv("BOT_REDIS_CONNECT_TIMEOUT_SECONDS", "1.5")
        monkeypatch.setenv("BOT_REDIS_SOCKET_TIMEOUT_SECONDS", "2.5")
        monkeypatch.setenv("BOT_REDIS_SOCKET_KEEPALIVE", "false")
        s = RedisSettings()
        assert s.url == "redis://prod.example.com:6379/1"
        assert s.pool_max_connections == 100
        assert s.connect_timeout_seconds == 1.5
        assert s.socket_timeout_seconds == 2.5
        assert s.socket_keepalive is False


class TestFieldInvariants:
    def test_pool_max_connections_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RedisSettings(pool_max_connections=0)

    def test_pool_max_connections_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RedisSettings(pool_max_connections=-1)

    def test_connect_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RedisSettings(connect_timeout_seconds=0.0)

    def test_socket_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RedisSettings(socket_timeout_seconds=0.0)
