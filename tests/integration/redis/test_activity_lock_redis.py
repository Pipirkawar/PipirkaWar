"""Integration-тесты `RedisActivityLockRepository` (Спринт 4.1-G, G.5).

Прогоняем happy/race/expiry-сценарии end-to-end через
`fakeredis.aioredis.FakeRedis` — in-memory подделку Redis-а,
поддерживающую корректную атомарность `SET NX PX` и TTL-логику
(`PTTL`/`EXPIRE`/`DEL`). Сетевого Redis-а не требуется.

Покрытие сверх unit-тестов:

* **Полный жизненный цикл**: try_acquire → второй try_acquire
  блокируется → release → try_acquire успешен.
* **Race-condition**: `asyncio.gather(try_acquire, try_acquire)` на
  один и тот же actor — ровно один из них возвращает `True`
  (SET NX-семантика).
* **Expired-lock cleanup через TTL**: эмулируем истёкший lock через
  ручное удаление key-а в FakeRedis (Redis-у aut-expire не нужен
  явный «тик» — TTL действует на следующей команде); проверяем,
  что новый try_acquire после "expiry" проходит.
* **JSON-payload round-trip через get**: после `try_acquire`
  → `get` возвращает `ActivityLock`-VO с правильным `reason`
  и `acquired_at`, восстановленным `expires_at = clock.now() + PTTL`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.domain.security import LockReason
from pipirik_wars.infrastructure.redis.repositories.activity_lock import (
    RedisActivityLockRepository,
)
from tests.fakes import FakeClock

_T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_TTL_2MIN = timedelta(minutes=2)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    """In-memory FakeRedis async-client (общий между sub-тестами scope=function)."""
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(_T0)


@pytest.fixture
def repo(redis_client: Redis, clock: FakeClock) -> RedisActivityLockRepository:
    return RedisActivityLockRepository(client=redis_client, clock=clock)


class TestRedisActivityLockRepositoryEndToEnd:
    async def test_acquire_blocked_release_acquire_again(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """Полный жизненный цикл: 1) acquire → 2) block → 3) release → 4) acquire."""
        ok1 = await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.FOREST,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        assert ok1 is True

        ok2 = await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.ORACLE,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        assert ok2 is False

        await repo.release(actor_kind="player", actor_id=1)

        ok3 = await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.ORACLE,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        assert ok3 is True

        # get → последний reason ORACLE.
        lock = await repo.get(actor_kind="player", actor_id=1)
        assert lock is not None
        assert lock.reason is LockReason.ORACLE

    async def test_concurrent_acquires_yield_exactly_one_winner(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """`asyncio.gather(try_acquire, try_acquire)` ⇒ ровно один True.

        `SET key value NX PX` атомарен в Redis-е (single-threaded
        command-execution); fakeredis ту же семантику соблюдает.
        """
        results = await asyncio.gather(
            *(
                repo.try_acquire(
                    actor_kind="player",
                    actor_id=7,
                    reason=LockReason.FOREST,
                    now=_T0,
                    expires_at=_T0 + _TTL_2MIN,
                )
                for _ in range(10)
            )
        )
        assert results.count(True) == 1
        assert results.count(False) == 9

    async def test_expired_lock_can_be_reacquired(
        self,
        repo: RedisActivityLockRepository,
        redis_client: Redis,
    ) -> None:
        """После истечения TTL новый try_acquire успешен.

        FakeRedis не двигает «время» автоматически — эмулируем
        истечение через явный `DEL` (как сделал бы Redis-сервер при
        TTL-watermark-е). Это тот же контракт, что в проде: Redis
        auto-удалит key, а наш repo увидит "key not found" на
        следующем SET NX.
        """
        await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.FOREST,
            now=_T0,
            expires_at=_T0 + timedelta(seconds=1),
        )
        # Эмулируем срабатывание TTL.
        await redis_client.delete("lock:player:1")

        ok = await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.ORACLE,
            now=_T0 + timedelta(minutes=5),
            expires_at=_T0 + timedelta(minutes=5) + _TTL_2MIN,
        )
        assert ok is True

    async def test_get_returns_activity_lock_with_correct_reason(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """JSON-payload-round-trip: acquire → get → правильный reason + acquired_at."""
        await repo.try_acquire(
            actor_kind="clan",
            actor_id=42,
            reason=LockReason.RAID,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        lock = await repo.get(actor_kind="clan", actor_id=42)
        assert lock is not None
        assert lock.actor_kind == "clan"
        assert lock.actor_id == 42
        assert lock.reason is LockReason.RAID
        assert lock.acquired_at == _T0
        # `expires_at` reconstructed как `clock.now() + PTTL`; clock не
        # двигался, так что близко к исходному `_T0 + _TTL_2MIN`
        # (±round-trip-в-fakeredis-ом).
        delta = abs((lock.expires_at - (_T0 + _TTL_2MIN)).total_seconds())
        assert delta < 1.0, f"expires_at off by {delta:.3f}s"

    async def test_different_actor_kinds_do_not_collide(
        self,
        repo: RedisActivityLockRepository,
    ) -> None:
        """`actor_kind` входит в key — `player:1` и `clan:1` независимы."""
        ok_player = await repo.try_acquire(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.FOREST,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        ok_clan = await repo.try_acquire(
            actor_kind="clan",
            actor_id=1,
            reason=LockReason.RAID,
            now=_T0,
            expires_at=_T0 + _TTL_2MIN,
        )
        assert (ok_player, ok_clan) == (True, True)
        # Sanity: оба lock-а присутствуют.
        assert (await repo.get(actor_kind="player", actor_id=1)) is not None
        assert (await repo.get(actor_kind="clan", actor_id=1)) is not None
