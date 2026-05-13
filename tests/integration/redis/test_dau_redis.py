"""Integration-тесты `RedisDauCounter` (Спринт 4.1-I, I.3).

Прогоняем full-lifecycle / dedup / cross-midnight / concurrent /
TTL-cleanup сценарии end-to-end через `fakeredis.aioredis.FakeRedis`
— in-memory подделку Redis-а, поддерживающую ZSET-команды
(`ZADD`/`ZCARD`/`ZSCORE`), pipeline-транзакции (`MULTI`/`EXEC`) и
TTL (`EXPIRE`/`TTL`/`DEL`). Сетевого Redis-а не требуется.

Покрытие сверх unit-тестов (которые на `..._test_dau.py`):

* **Полный жизненный цикл**: 0 → record_active(3 разных) → current=3
  → новый МСК-день → current=0 → record_active(новый) → current=1.
* **Dedup-инвариант** через ZADD-score: повторный `record_active`
  того же `tg_user_id` обновляет score, ZCARD остаётся 1.
* **Cross-midnight cleanup**: «вчерашний» key продолжает существовать
  после полуночи (TTL 48h), но `current()` опирается на key текущего
  дня. Эмулируем истечение TTL через ручной `DEL` (Redis-семантика
  «по TTL» = ключ удаляется на следующей команде после expiry; для
  чёрного ящика это идентично `DEL`).
* **Concurrent record_active(50× distinct users)** через
  `asyncio.gather` — все 50 попадают в ZSET, `current() == 50`
  (atomicity pipeline-а сохраняется в fakeredis).
* **Concurrent record_active(10× same user)** — счётчик == 1
  (ZADD-idempotency).
* **Изоляция между `key_prefix`-ами**: два экземпляра с разными
  префиксами работают над непересекающимися ключами.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.infrastructure.redis.repositories.dau import RedisDauCounter
from tests.fakes import FakeClock

_MOSCOW_TZ = timezone(timedelta(hours=3))
_T0_MSK_NOON = datetime(2026, 5, 5, 12, 0, tzinfo=_MOSCOW_TZ).astimezone(UTC)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    """In-memory FakeRedis async-client (scope=function — fresh между тестами)."""
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def clock() -> FakeClock:
    return FakeClock(_T0_MSK_NOON)


@pytest_asyncio.fixture
async def counter(redis_client: Redis, clock: FakeClock) -> RedisDauCounter:
    return RedisDauCounter(client=redis_client, clock=clock)


class TestRedisDauCounterEndToEnd:
    async def test_full_lifecycle(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        """0 → 3 уникальных → 3; новый МСК-день → 0 → +1 → 1."""
        assert await counter.current() == 0

        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        await counter.record_active(tg_user_id=333)
        assert await counter.current() == 3

        # Сдвиг на сутки вперёд — наступил следующий МСК-день.
        clock.advance(days=1)
        assert await counter.current() == 0

        await counter.record_active(tg_user_id=444)
        assert await counter.current() == 1

    async def test_dedup_through_zadd_score_invariant(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
        redis_client: Redis,
    ) -> None:
        """Повторный record_active того же актера = update score, не дубль.

        ZADD на существующий member обновляет score, но `ZCARD` остаётся
        прежним. Sanity-проверка по score-значению: после 2-го вызова
        через 2 часа score-у пользователя именно второй timestamp.
        """
        moment_first = _T0_MSK_NOON
        clock.set(moment_first)
        await counter.record_active(tg_user_id=111)
        score_first = await redis_client.zscore("dau:2026-05-05", "111")

        clock.advance(hours=2)
        moment_second = moment_first + timedelta(hours=2)
        await counter.record_active(tg_user_id=111)
        score_second = await redis_client.zscore("dau:2026-05-05", "111")

        assert await counter.current() == 1
        assert score_first is not None
        assert score_second is not None
        assert score_first < score_second
        # Score-инвариант: совпадает с timestamp-ом момента вызова
        # (с точностью до float-погрешности).
        assert abs(score_second - moment_second.timestamp()) < 1e-3

    async def test_cross_midnight_yesterday_key_still_alive(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
        redis_client: Redis,
    ) -> None:
        """48h TTL: «вчерашний» key жив, но `current()` смотрит на сегодня.

        После полуночи МСК `current()` возвращает 0 (новый key пуст),
        но «вчерашний» key остаётся в Redis-е (TTL = 48h) — его можно
        прочитать командой `redis.zcard` напрямую (для cron-снапшота
        DAU прошлого дня в будущей аналитике).
        """
        # День 1: 2026-05-05 МСК.
        clock.set(_T0_MSK_NOON)
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        # Шаг в день 2: 2026-05-06 МСК.
        clock.advance(days=1)
        # `current()` для сегодня = 0.
        assert await counter.current() == 0
        # Но «вчерашний» key всё ещё лежит в Redis-е с обоими actor-ами.
        assert await redis_client.zcard("dau:2026-05-05") == 2

    async def test_ttl_expiry_emulation_clears_key(
        self,
        counter: RedisDauCounter,
        redis_client: Redis,
    ) -> None:
        """Эмуляция TTL-expiry: ручной `DEL` для «истёкшего» key-а.

        Через 48h Redis удалит key автоматически. Эффект (с точки
        зрения чёрного ящика) идентичен `redis.delete(...)`: после
        этого `current()` для того же дня вернёт 0 как для пустого
        ZSET-а.
        """
        await counter.record_active(tg_user_id=111)
        assert await counter.current() == 1
        # Эмулируем «прошло 48 часов и TTL сработал».
        await redis_client.delete("dau:2026-05-05")
        assert await counter.current() == 0

    async def test_concurrent_record_active_distinct_users(
        self,
        counter: RedisDauCounter,
    ) -> None:
        """asyncio.gather(50× distinct users) ⇒ count == 50.

        Все 50 параллельных `record_active` с разными `tg_user_id`
        попадают в ZSET, ни одно не теряется. Pipeline ZADD+EXPIRE
        атомарен (single-threaded Redis-execution).
        """
        await asyncio.gather(*(counter.record_active(tg_user_id=i) for i in range(50)))
        assert await counter.current() == 50

    async def test_concurrent_record_active_same_user(
        self,
        counter: RedisDauCounter,
    ) -> None:
        """asyncio.gather(10× same user) ⇒ count == 1.

        ZADD-idempotency: тот же `tg_user_id` 10 раз — counter не
        растёт (ZADD на существующий member обновляет score, member-а
        не дублирует).
        """
        await asyncio.gather(*(counter.record_active(tg_user_id=42) for _ in range(10)))
        assert await counter.current() == 1

    async def test_key_prefix_isolation(
        self,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        """Два экземпляра с разными `key_prefix` работают изолированно."""
        prod = RedisDauCounter(client=redis_client, clock=clock, key_prefix="dau")
        shadow = RedisDauCounter(client=redis_client, clock=clock, key_prefix="shadow-dau")

        # 3 в prod, 1 в shadow.
        await prod.record_active(tg_user_id=111)
        await prod.record_active(tg_user_id=222)
        await prod.record_active(tg_user_id=333)
        await shadow.record_active(tg_user_id=999)

        assert await prod.current() == 3
        assert await shadow.current() == 1
        # И на низком уровне ключи не пересекаются.
        assert await redis_client.zcard("dau:2026-05-05") == 3
        assert await redis_client.zcard("shadow-dau:2026-05-05") == 1
