"""Unit-тесты `RedisGlobalLobbyRepository` (Спринт 4.1-H, шаг H.1).

Покрытие через `fakeredis.aioredis.FakeRedis` — async-fake-Redis, который
поддерживает Lua-скрипты (`EVALSHA` + `SCRIPT LOAD`), LIST-операции
(`LPUSH`/`RPOP`/`LREM`/`LLEN`/`LRANGE`) и HASH-операции
(`HEXISTS`/`HSET`/`HGET`/`HDEL`/`HLEN`).

Тесты:

* ``enqueue`` happy-path — первый вызов возвращает True; запись попадает
  в LIST и HASH.
* ``enqueue`` dedup — повторный вызов на тот же ``duel_id`` возвращает
  False, **сохраняет первоначальный `enqueued_at`** (контракт FIFO-
  идемпотентности).
* ``pop_oldest`` happy-path — возвращает первую попавшую запись,
  очищает HASH.
* ``pop_oldest`` на пустой очереди возвращает None.
* ``pop_oldest`` FIFO-ordering — три записи, pop-ает в порядке enqueue-а.
* ``remove`` — happy-path и NO-OP-кейс (записи нет).
* ``is_in_lobby`` — True для существующей, False для отсутствующей.
* Key-format и кастомный `key_prefix` пробрасываются корректно.
* Concurrent `enqueue` на один ``duel_id`` через `asyncio.gather` —
  ровно один из 10 вызовов возвращает True (Lua-atomicity).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.infrastructure.redis.repositories.global_lobby import (
    RedisGlobalLobbyRepository,
)

_NOW = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest.fixture
def repo(redis_client: Redis) -> RedisGlobalLobbyRepository:
    return RedisGlobalLobbyRepository(client=redis_client)


class TestEnqueue:
    async def test_first_enqueue_returns_true(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        ok = await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert ok is True

    async def test_second_enqueue_same_duel_returns_false(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        ok = await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert ok is False

    async def test_second_enqueue_preserves_original_enqueued_at(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """Повторный enqueue не двигает первоначальный `enqueued_at` (FIFO)."""
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        later = _NOW.replace(hour=12)
        ok = await repo.enqueue(duel_id=42, enqueued_at=later)
        assert ok is False
        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 42
        assert entry.enqueued_at == _NOW

    async def test_enqueue_different_duels_both_succeed(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        ok1 = await repo.enqueue(duel_id=1, enqueued_at=_NOW)
        ok2 = await repo.enqueue(duel_id=2, enqueued_at=_NOW)
        assert ok1 is True
        assert ok2 is True

    async def test_enqueue_writes_list_and_hash(
        self,
        repo: RedisGlobalLobbyRepository,
        redis_client: Redis,
    ) -> None:
        """Sanity-check key-format: после enqueue LIST и HASH непустые."""
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert await redis_client.llen("lobby:queue") == 1
        assert await redis_client.hexists("lobby:enqueued_at", "42") == 1
        iso_raw = await redis_client.hget("lobby:enqueued_at", "42")
        assert iso_raw is not None
        iso = iso_raw.decode("utf-8") if isinstance(iso_raw, bytes) else iso_raw
        assert iso == _NOW.isoformat()


class TestPopOldest:
    async def test_pop_oldest_on_empty_returns_none(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        entry = await repo.pop_oldest()
        assert entry is None

    async def test_pop_oldest_returns_enqueued_entry(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 42
        assert entry.enqueued_at == _NOW

    async def test_pop_oldest_clears_hash_field(
        self,
        repo: RedisGlobalLobbyRepository,
        redis_client: Redis,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        await repo.pop_oldest()
        assert await redis_client.hexists("lobby:enqueued_at", "42") == 0
        assert await redis_client.llen("lobby:queue") == 0

    async def test_pop_oldest_fifo_ordering(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """Три enqueue → три pop — порядок строго по моменту enqueue."""
        t1 = _NOW
        t2 = _NOW.replace(minute=5)
        t3 = _NOW.replace(minute=10)
        await repo.enqueue(duel_id=1, enqueued_at=t1)
        await repo.enqueue(duel_id=2, enqueued_at=t2)
        await repo.enqueue(duel_id=3, enqueued_at=t3)
        e1 = await repo.pop_oldest()
        e2 = await repo.pop_oldest()
        e3 = await repo.pop_oldest()
        assert e1 is not None and e1.duel_id == 1 and e1.enqueued_at == t1
        assert e2 is not None and e2.duel_id == 2 and e2.enqueued_at == t2
        assert e3 is not None and e3.duel_id == 3 and e3.enqueued_at == t3
        assert await repo.pop_oldest() is None


class TestRemove:
    async def test_remove_existing_returns_true(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        ok = await repo.remove(duel_id=42)
        assert ok is True

    async def test_remove_missing_returns_false(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        ok = await repo.remove(duel_id=42)
        assert ok is False

    async def test_remove_clears_both_list_and_hash(
        self,
        repo: RedisGlobalLobbyRepository,
        redis_client: Redis,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        await repo.remove(duel_id=42)
        assert await redis_client.llen("lobby:queue") == 0
        assert await redis_client.hexists("lobby:enqueued_at", "42") == 0

    async def test_remove_does_not_touch_other_entries(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=1, enqueued_at=_NOW)
        await repo.enqueue(duel_id=2, enqueued_at=_NOW)
        await repo.remove(duel_id=1)
        assert await repo.is_in_lobby(duel_id=1) is False
        assert await repo.is_in_lobby(duel_id=2) is True


class TestIsInLobby:
    async def test_is_in_lobby_true_after_enqueue(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert await repo.is_in_lobby(duel_id=42) is True

    async def test_is_in_lobby_false_for_absent(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        assert await repo.is_in_lobby(duel_id=42) is False

    async def test_is_in_lobby_false_after_pop_oldest(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        await repo.pop_oldest()
        assert await repo.is_in_lobby(duel_id=42) is False


class TestKeyPrefix:
    async def test_custom_key_prefix(self, redis_client: Redis) -> None:
        repo = RedisGlobalLobbyRepository(client=redis_client, key_prefix="custom-lobby")
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert await redis_client.llen("custom-lobby:queue") == 1
        assert await redis_client.hexists("custom-lobby:enqueued_at", "42") == 1
        # default-prefix не задет
        assert await redis_client.exists("lobby:queue") == 0


class TestAtomicity:
    async def test_concurrent_enqueue_same_duel_yields_one_winner(
        self,
        repo: RedisGlobalLobbyRepository,
    ) -> None:
        """asyncio.gather(10× enqueue same duel) ⇒ ровно один True.

        Lua-скрипт ``HEXISTS → HSET + LPUSH`` атомарен (single-threaded
        Redis-execution); fakeredis сохраняет ту же семантику.
        """
        results = await asyncio.gather(
            *(repo.enqueue(duel_id=7, enqueued_at=_NOW) for _ in range(10))
        )
        assert results.count(True) == 1
        assert results.count(False) == 9
        # Очередь содержит ровно одну запись.
        entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == 7
        assert await repo.pop_oldest() is None
