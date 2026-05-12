"""Настройки Redis-инфраструктуры (Спринт 4.1-G, шаг G.2).

Pydantic-settings-секция `BOT_REDIS_*`. Все значения — из env (или
`.env` локально, который в `.gitignore`). Дефолты — local-dev-friendly:
`redis://localhost:6379/0`, пул 20 connections, 5-секундные таймауты,
keepalive on.

Композиционный root (`bot/main.py`, шаг G.4) создаёт
`build_redis_client(settings.redis)` ровно один раз и переиспользует
singleton для всех Redis-репозиториев (long-lived connection-pool —
best-practice для `redis-py >= 5.0`).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["RedisSettings"]


class RedisSettings(BaseSettings):
    """Конфигурация Redis-инфраструктуры (Спринт 4.1-G, G.2).

    Поля:

    * ``url`` — Redis connection-URL (`redis://[:password@]host:port/db`
      или `rediss://...` для TLS). Дефолт — local-dev (`redis://localhost:6379/0`).
    * ``pool_max_connections`` — лимит одновременных соединений в
      `ConnectionPool`-е. Дефолт `20` — достаточно для MVP DAU=200.
    * ``connect_timeout_seconds`` — таймаут TCP-handshake-а.
    * ``socket_timeout_seconds`` — таймаут чтения/записи в socket.
    * ``socket_keepalive`` — включить TCP-keepalive на сокете
      (детектирует висящие соединения после network-glitch-ей).
    """

    model_config = SettingsConfigDict(
        env_prefix="BOT_REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(
        default="redis://localhost:6379/0",
        description=(
            "Redis connection-URL: `redis://[:password@]host:port/db` или "
            "`rediss://...` для TLS. Дефолт — local-dev."
        ),
    )
    pool_max_connections: int = Field(
        default=20,
        gt=0,
        description=(
            "Лимит одновременных соединений в `ConnectionPool`-е. "
            "Дефолт `20` — достаточно для MVP DAU=200."
        ),
    )
    connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        description="Таймаут TCP-handshake-а в секундах.",
    )
    socket_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        description="Таймаут чтения/записи в socket в секундах.",
    )
    socket_keepalive: bool = Field(
        default=True,
        description=(
            "Включить TCP-keepalive на сокете (детектирует висящие "
            "соединения после network-glitch-ей)."
        ),
    )
