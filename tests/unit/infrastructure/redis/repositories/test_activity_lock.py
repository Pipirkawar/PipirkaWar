"""Unit-тесты `RedisActivityLockRepository` (Спринт 4.1-G, шаг G.3).

Покрытие через `fakeredis.aioredis.FakeRedis`:

* ``try_acquire`` happy-path (первый вызов → True; key создан с правильным
  payload-ом и TTL).
* ``try_acquire`` NX-conflict (второй вызов на тот же актор → False).
* ``try_acquire`` после ``release`` → True (release удалил key).
* ``try_acquire`` с уже-истёкшим ``expires_at`` (`ttl_ms <= 0`) →
  False без обращения к Redis.
* ``try_acquire`` разные акторы не конфликтуют (разные key-ы).
* ``release`` — NO-OP если key не существует.
* ``get`` — None если key не существует.
* ``get`` — возвращает `ActivityLock` с правильными `reason`/`acquired_at`
  и реконструированным `expires_at` (`clock.now() + PTTL`).
* ``get`` — None после истечения TTL (Redis auto-delete).
* Key-format: ``lock:{actor_kind}:{actor_id}`` (sanity-check через
  прямое чтение из FakeRedis).
* Кастомный ``key_prefix`` пробрасывается в key-format.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.domain.security import ActivityLock, LockReason
from pipirik_wars.infrastructure.redis.repositories.activity_lock import (
    RedisActivityLockRepository,
)
from tests.fakes import FakeClock

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_TTL = timedelta(minutes=10)
_EXPIRES_AT = _NOW + _TTL


@pytest.fixture
async def redis_client() -> Redis:
    """In-memory FakeRedis async-client (по умолчанию decode_responses=False)."""
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(_NOW)


@pytest.fixture
def repo(redis_client: Redis, clock: FakeClock) -> RedisActivityLockRepository:
    return RedisActivityLockRepository(client=redis_client, clock=clock)


class TestTryAcquire:
    async def test_first_acquire_returns_true(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        assert ok is True

    async def test_second_acquire_same_actor_returns_false(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.DUNGEON,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        assert ok is False

    async def test_acquire_after_release_returns_true(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        await repo.release(actor_kind="player", actor_id=42)
        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.DUNGEON,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        assert ok is True

    async def test_acquire_with_non_positive_ttl_returns_false(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """expires_at <= now ⇒ ttl_ms <= 0 ⇒ Redis отверг бы SET PX.

        Repository fail-safe: возвращает False без обращения к Redis.
        """
        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_NOW,
        )
        assert ok is False
        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_NOW - timedelta(seconds=1),
        )
        assert ok is False

    async def test_different_actors_do_not_conflict(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        ok1 = await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        ok2 = await repo.try_acquire(
            actor_kind="player",
            actor_id=43,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        ok3 = await repo.try_acquire(
            actor_kind="clan",
            actor_id=42,
            reason=LockReason.RAID,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        assert (ok1, ok2, ok3) == (True, True, True)

    async def test_key_format_and_payload(
        self,
        repo: RedisActivityLockRepository,
        redis_client: Redis,
    ) -> None:
        """Sanity: key = `lock:{actor_kind}:{actor_id}`; value = JSON."""
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        raw = await redis_client.get("lock:player:42")
        assert raw is not None
        data = json.loads(raw)
        assert data == {
            "reason": LockReason.FOREST.value,
            "acquired_at": _NOW.isoformat(),
        }
        # TTL пришёл в Redis: PTTL > 0 и <= ttl_ms (вычитая мс между SET и PTTL).
        pttl_ms = await redis_client.pttl("lock:player:42")
        assert 0 < pttl_ms <= int(_TTL.total_seconds() * 1000)


class TestRelease:
    async def test_release_existing_lock_removes_key(
        self,
        repo: RedisActivityLockRepository,
        redis_client: Redis,
    ) -> None:
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        await repo.release(actor_kind="player", actor_id=42)
        assert await redis_client.get("lock:player:42") is None

    async def test_release_missing_lock_is_noop(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """`DEL` на отсутствующем ключе не падает (Redis возвращает 0)."""
        await repo.release(actor_kind="player", actor_id=999)


class TestGet:
    async def test_get_returns_none_when_no_lock(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        result = await repo.get(actor_kind="player", actor_id=42)
        assert result is None

    async def test_get_returns_activity_lock_when_present(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        result = await repo.get(actor_kind="player", actor_id=42)
        assert isinstance(result, ActivityLock)
        assert result.actor_kind == "player"
        assert result.actor_id == 42
        assert result.reason is LockReason.FOREST
        assert result.acquired_at == _NOW
        # expires_at — clock.now() + PTTL; clock не двигался, так что
        # должно быть очень близко к _EXPIRES_AT (с учётом round-trip-а).
        delta = abs((result.expires_at - _EXPIRES_AT).total_seconds())
        assert delta < 1.0, f"expires_at off by {delta:.3f}s"

    async def test_get_returns_none_after_ttl_expiry(
        self,
        repo: RedisActivityLockRepository,
        redis_client: Redis,
    ) -> None:
        """После истечения TTL Redis auto-удаляет key; `get` → None."""
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_NOW + timedelta(milliseconds=50),
        )
        # Принудительно delete-ом эмулируем срабатывание TTL (fakeredis
        # auto-expire срабатывает не на каждой команде; явный DEL —
        # детерминированный путь).
        await redis_client.delete("lock:player:42")
        result = await repo.get(actor_kind="player", actor_id=42)
        assert result is None

    async def test_get_after_clock_advance_recomputes_expires_at(
        self,
        repo: RedisActivityLockRepository,
        clock: FakeClock,
    ) -> None:
        """`expires_at = clock.now() + PTTL`: если clock двинулся, expires_at двигается."""
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        clock.advance(minutes=2)
        result = await repo.get(actor_kind="player", actor_id=42)
        assert result is not None
        # expires_at должно быть _NOW + 10min исходно, но при PTTL он
        # пересчитан от текущего clock.now(). Поэтому остаточный TTL
        # ~ 8min от нового момента.
        remaining = (result.expires_at - clock.now()).total_seconds()
        assert 0 < remaining <= int(_TTL.total_seconds())


class TestCustomKeyPrefix:
    async def test_key_prefix_overrides_default(
        self,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        repo = RedisActivityLockRepository(
            client=redis_client,
            clock=clock,
            key_prefix="pipirik:lock",
        )
        await repo.try_acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_EXPIRES_AT,
        )
        # Кастомный prefix — key должен быть `pipirik:lock:player:42`.
        assert await redis_client.get("pipirik:lock:player:42") is not None
        # А дефолтного `lock:player:42` НЕ должно существовать.
        assert await redis_client.get("lock:player:42") is None
