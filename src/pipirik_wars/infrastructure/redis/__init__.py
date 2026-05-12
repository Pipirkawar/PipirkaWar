"""Redis infrastructure adapters (Спринт 4.1-G).

Реализации портов `IActivityLockRepository` (G.3), а в последующих PR-ах
— Lobby (4.1-H) и DAU (4.1-I) поверх `redis.asyncio.Redis` (async-native
Redis-клиент, выпускается официальным `redis-py` >= 5.0 как преемник
`aioredis` 2.x).

Структура:

* `settings` — `RedisSettings` (`pydantic-settings`, prefix `BOT_REDIS_`),
  читается из env / `.env`; включает URL, размер пула, таймауты.
* `client` — фабрика `build_redis_client(settings) -> redis.asyncio.Redis`
  с явным `ConnectionPool`-ом (long-lived singleton, переиспользуется
  всеми Redis-репозиториями в composition root-е).
* `repositories/` — Redis-имплементации репозиториев (G.3 и далее).

Композиционный root (`bot/main.py`, шаг G.4) переключает между
SQL-backend-ом (default) и Redis-backend-ом через
`Settings.activity_lock_backend: Literal["sql","redis"]` (env
`BOT_ACTIVITY_LOCK_BACKEND`). До G.4 этот модуль в проде не
импортируется — только тестами G.2/G.3.
"""

from pipirik_wars.infrastructure.redis.client import build_redis_client
from pipirik_wars.infrastructure.redis.settings import RedisSettings

__all__ = [
    "RedisSettings",
    "build_redis_client",
]
