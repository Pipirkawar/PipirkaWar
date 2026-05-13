"""Integration-тесты `RedisGlobalLobbyRepository` (Спринт 4.1-H, H.3).

Прогоняем full-lifecycle / dedup / concurrency / atomicity-сценарии
end-to-end через `fakeredis.aioredis.FakeRedis` — in-memory подделку
Redis-а, поддерживающую LIST/HASH-команды и Lua-скрипты (через
`fakeredis[lua]` extra → `lupa`). Сетевого Redis-а не требуется.

Покрытие сверх unit-тестов (которые на `..._global_lobby.py`):

* **Полный жизненный цикл**: enqueue → is_in_lobby=True → pop_oldest
  возвращает запись → is_in_lobby=False.
* **Multi-актёры**: 3 разных `duel_id` встают в очередь, pop_oldest
  возвращает их в FIFO-порядке.
* **Dedup**: повторный `enqueue` на тот же `duel_id` возвращает
  False и **сохраняет первоначальный `enqueued_at`**.
* **remove (отмена дуэли)**: enqueue → remove → is_in_lobby=False
  → pop_oldest возвращает None (запись стёрта и из LIST, и из HASH).
* **Concurrent enqueue** на один `duel_id` через `asyncio.gather`:
  ровно один из 10 параллельных вызовов возвращает True (Lua-
  атомарность `HEXISTS → HSET + LPUSH`).
* **Atomicity-инвариант** после `pop_oldest`: ни LIST, ни HASH
  не содержат следов извлечённой записи (одной транзакцией).
* **Изоляция между `key_prefix`-ами**: два экземпляра с разными
  префиксами работают над непересекающимися ключами.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.infrastructure.redis.repositories.global_lobby import (
    RedisGlobalLobbyRepository,
)

_T0 = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    """In-memory FakeRedis async-client (общий между sub-тестами scope=function)."""
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def repo(redis_client: Redis) -> RedisGlobalLobbyRepository:
    return RedisGlobalLobbyRepository(client=redis_client)


class TestRedisGlobalLobbyRepositoryEndToEnd:
    async def test_full_lifecycle(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """Полный жизненный цикл: enqueue → is_in_lobby → pop_oldest → empty."""
        ok = await repo.enqueue(duel_id=42, enqueued_at=_T0)
        assert ok is True
        assert await repo.is_in_lobby(duel_id=42) is True

        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 42
        assert entry.enqueued_at == _T0

        # Очередь пуста, повторный pop_oldest возвращает None.
        assert await repo.pop_oldest() is None
        assert await repo.is_in_lobby(duel_id=42) is False

    async def test_three_actors_fifo_order(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """Три разных дуэли встают в очередь, pop_oldest возвращает их FIFO."""
        t1 = _T0
        t2 = _T0 + timedelta(seconds=30)
        t3 = _T0 + timedelta(seconds=60)
        assert await repo.enqueue(duel_id=1, enqueued_at=t1) is True
        assert await repo.enqueue(duel_id=2, enqueued_at=t2) is True
        assert await repo.enqueue(duel_id=3, enqueued_at=t3) is True

        e1 = await repo.pop_oldest()
        e2 = await repo.pop_oldest()
        e3 = await repo.pop_oldest()
        assert e1 is not None and e1.duel_id == 1 and e1.enqueued_at == t1
        assert e2 is not None and e2.duel_id == 2 and e2.enqueued_at == t2
        assert e3 is not None and e3.duel_id == 3 and e3.enqueued_at == t3

    async def test_dedup_preserves_original_enqueued_at(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """Повторный `enqueue` на тот же `duel_id` ⇒ False; `enqueued_at` не сдвигается."""
        assert await repo.enqueue(duel_id=42, enqueued_at=_T0) is True
        later = _T0 + timedelta(hours=1)
        assert await repo.enqueue(duel_id=42, enqueued_at=later) is False

        # is_in_lobby по-прежнему True; pop_oldest возвращает оригинальный TS.
        assert await repo.is_in_lobby(duel_id=42) is True
        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 42
        assert entry.enqueued_at == _T0

    async def test_remove_clears_from_queue(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """enqueue → remove → is_in_lobby=False → pop_oldest=None."""
        await repo.enqueue(duel_id=42, enqueued_at=_T0)
        ok = await repo.remove(duel_id=42)
        assert ok is True

        assert await repo.is_in_lobby(duel_id=42) is False
        assert await repo.pop_oldest() is None

    async def test_concurrent_enqueue_yields_single_winner(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """`asyncio.gather(10× enqueue same duel)` ⇒ ровно 1 True.

        Lua-скрипт `HEXISTS → HSET + LPUSH` атомарен (single-threaded
        Redis-execution); fakeredis ту же семантику соблюдает.
        """
        results = await asyncio.gather(
            *(repo.enqueue(duel_id=7, enqueued_at=_T0) for _ in range(10))
        )
        assert results.count(True) == 1
        assert results.count(False) == 9

        # Очередь содержит ровно одну запись.
        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 7
        assert await repo.pop_oldest() is None

    async def test_pop_oldest_atomicity_invariant(
        self,
        repo: RedisGlobalLobbyRepository,
        redis_client: Redis,
    ) -> None:
        """После `pop_oldest` НИ LIST, НИ HASH не содержат следов извлечения.

        Атомарный Lua-скрипт `RPOP → HGET + HDEL` должен оставлять обе
        структуры в консистентном состоянии — partial-state (только LIST
        стёрт или только HASH стёрт) делает is_in_lobby несогласованным
        с реальным наличием записи в очереди.
        """
        await repo.enqueue(duel_id=42, enqueued_at=_T0)
        await repo.pop_oldest()

        assert await redis_client.llen("lobby:queue") == 0
        assert await redis_client.hlen("lobby:enqueued_at") == 0
        # is_in_lobby в `False` — последний штрих к инварианту.
        assert await repo.is_in_lobby(duel_id=42) is False

    async def test_key_prefix_isolation(
        self,
        redis_client: Redis,
    ) -> None:
        """Два экземпляра с разными `key_prefix`-ами работают над разными ключами."""
        repo_a = RedisGlobalLobbyRepository(client=redis_client, key_prefix="lobby-a")
        repo_b = RedisGlobalLobbyRepository(client=redis_client, key_prefix="lobby-b")

        await repo_a.enqueue(duel_id=1, enqueued_at=_T0)
        await repo_b.enqueue(duel_id=1, enqueued_at=_T0)

        # Оба видят свою запись (одинаковый duel_id, разные пространства).
        assert await repo_a.is_in_lobby(duel_id=1) is True
        assert await repo_b.is_in_lobby(duel_id=1) is True

        # pop_oldest на A не задевает B.
        await repo_a.pop_oldest()
        assert await repo_a.is_in_lobby(duel_id=1) is False
        assert await repo_b.is_in_lobby(duel_id=1) is True
