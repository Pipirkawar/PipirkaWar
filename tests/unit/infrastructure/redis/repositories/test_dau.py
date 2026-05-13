"""Unit-тесты `RedisDauCounter` (Спринт 4.1-I, шаг I.1).

Покрытие через `fakeredis.aioredis.FakeRedis` — async-fake-Redis,
поддерживает ZSET-команды (`ZADD`/`ZCARD`/`ZSCORE`), `EXPIRE`/`TTL`,
pipeline-транзакции (`MULTI`/`EXEC`). Сетевого Redis-а не требуется.

Тесты (по аналогии с `InMemoryDauCounter`-набором):

* Пустой счётчик возвращает 0.
* ``record_active`` — уникальные актёры считаются ровно один раз
  (повторный `record_active` того же `tg_user_id` не увеличивает
  `current()`).
* Граница дня по `Europe/Moscow` — счётчик «сбрасывается» в момент
  перехода через 00:00 МСК (на стороне Redis-а это смена key-а).
* «Сегодня» внутри одного МСК-дня остаётся стабильным.
* Lazy-reset: если бот «спал» через полночь, первый `current()` после
  полуночи МСК возвращает 0 (новый key пуст).
* `record_active` после lazy-reset стартует с чистого счётчика.
* МСК-таймзона для границы дня учитывается (UTC 22:00 = МСК 01:00
  следующего дня).
* Key-format `dau:{YYYY-MM-DD}` + кастомный `key_prefix`
  пробрасываются корректно.
* `EXPIRE` 48h выставляется после `record_active`.
* `ZADD` пишет score = unix-timestamp (для будущей аналитики через
  `ZRANGEBYSCORE`).
* Concurrent `record_active` на одного и того же актера через
  `asyncio.gather(10×)` — счётчик равен 1 (ZADD-idempotency).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from pipirik_wars.infrastructure.redis.repositories.dau import RedisDauCounter
from tests.fakes import FakeClock

_MOSCOW_TZ = timezone(timedelta(hours=3))
_TTL_SECONDS_48H = 172_800


def _msk(year: int, month: int, day: int, hour: int = 12) -> datetime:
    """Сконструировать момент в МСК (через UTC-конверсию — `IClock` в `Settings`)."""
    return datetime(year, month, day, hour, tzinfo=_MOSCOW_TZ).astimezone(UTC)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    client = FakeRedis()
    try:
        yield cast(Redis, client)
    finally:
        await client.aclose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(_msk(2026, 5, 4, hour=12))


@pytest.fixture
def counter(redis_client: Redis, clock: FakeClock) -> RedisDauCounter:
    return RedisDauCounter(client=redis_client, clock=clock)


class TestEmpty:
    async def test_empty_counter_starts_at_zero(
        self,
        counter: RedisDauCounter,
    ) -> None:
        assert await counter.current() == 0


class TestRecordActive:
    async def test_record_active_counts_unique_users(
        self,
        counter: RedisDauCounter,
    ) -> None:
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        # Дубль — не должен увеличить счётчик.
        await counter.record_active(tg_user_id=111)
        assert await counter.current() == 2

    async def test_record_active_writes_zset_with_correct_key(
        self,
        counter: RedisDauCounter,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        """Key-format: `dau:{YYYY-MM-DD}` по МСК-дню."""
        clock.set(_msk(2026, 5, 4, hour=10))
        await counter.record_active(tg_user_id=111)
        assert await redis_client.zcard("dau:2026-05-04") == 1
        # Запись попала в default-prefix; никаких других prefix-ов
        # не задето.
        assert await redis_client.exists("dau:2026-05-03") == 0
        assert await redis_client.exists("dau:2026-05-05") == 0

    async def test_record_active_stores_timestamp_as_score(
        self,
        counter: RedisDauCounter,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        """Score `tg_user_id`-члена — Unix-timestamp момента `record_active`.

        Это контрактное поведение — позволяет аналитике через
        ``ZRANGEBYSCORE`` собирать активных в произвольном временном
        окне (отложено за пределы 4.1-I, но фундамент закладывается).
        """
        moment = _msk(2026, 5, 4, hour=10)
        clock.set(moment)
        await counter.record_active(tg_user_id=111)
        score = await redis_client.zscore("dau:2026-05-04", "111")
        assert score is not None
        assert score == pytest.approx(moment.timestamp())

    async def test_record_active_sets_ttl(
        self,
        counter: RedisDauCounter,
        redis_client: Redis,
    ) -> None:
        """После `record_active` на key выставлен TTL ≈ 48h."""
        await counter.record_active(tg_user_id=111)
        ttl = await redis_client.ttl("dau:2026-05-04")
        # TTL в секундах. fakeredis возвращает целое; допустим небольшой
        # дрейф вниз (хотя real Redis всегда возвращает [TTL_SECONDS;TTL_SECONDS])
        # — берём диапазон [_TTL_SECONDS_48H - 5; _TTL_SECONDS_48H].
        assert _TTL_SECONDS_48H - 5 <= ttl <= _TTL_SECONDS_48H

    async def test_repeated_record_active_updates_score_not_count(
        self,
        counter: RedisDauCounter,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        """Повторный `record_active` обновляет score, но не плодит дубли.

        Это контрактная семантика `ZADD` — для уже существующего члена
        он обновляет score, но `ZCARD` остаётся прежним.
        """
        clock.set(_msk(2026, 5, 4, hour=10))
        await counter.record_active(tg_user_id=111)
        score_first = await redis_client.zscore("dau:2026-05-04", "111")
        # Через 2 часа.
        clock.advance(hours=2)
        await counter.record_active(tg_user_id=111)
        score_second = await redis_client.zscore("dau:2026-05-04", "111")
        assert await counter.current() == 1
        assert score_first is not None
        assert score_second is not None
        # Score обновлён на новый timestamp.
        assert score_second > score_first


class TestMoscowDayBoundary:
    async def test_resets_on_new_moscow_day(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        clock.set(_msk(2026, 5, 4, hour=23))
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

        # Переход через полночь МСК (на 2 часа вперёд → 01:00 5 мая МСК).
        clock.advance(hours=2)
        assert await counter.current() == 0  # сброс через смену key-а

        await counter.record_active(tg_user_id=333)
        assert await counter.current() == 1

    async def test_no_reset_within_same_moscow_day(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        clock.set(_msk(2026, 5, 4, hour=1))
        await counter.record_active(tg_user_id=111)
        # 22 часа спустя — всё ещё 4 мая МСК (с 01:00 до 23:00).
        clock.advance(hours=22)
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

    async def test_reset_lazy_only_on_first_call_after_midnight(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        """Если бот «спал» через полночь — первый вызов после возврата
        нового МСК-дня возвращает 0 (key для нового дня ещё не создан).
        """
        clock.set(_msk(2026, 5, 4, hour=23))
        await counter.record_active(tg_user_id=111)
        clock.advance(days=2)  # перешли в 6 мая МСК
        assert await counter.current() == 0

    async def test_record_active_after_reset_starts_fresh(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        clock.set(_msk(2026, 5, 4, hour=23))
        await counter.record_active(tg_user_id=111)
        clock.advance(hours=2)  # 5 мая 01:00 МСК
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

    async def test_uses_moscow_timezone_for_day_boundary(
        self,
        counter: RedisDauCounter,
        clock: FakeClock,
    ) -> None:
        """4 мая 22:00 UTC = 5 мая 01:00 МСК — счётчик уже на 5-м дне."""
        clock.set(datetime(2026, 5, 4, 22, 0, tzinfo=UTC))
        await counter.record_active(tg_user_id=111)

        # UTC 5 мая 01:00 = МСК 04:00 — всё ещё 5-й день МСК.
        clock.set(datetime(2026, 5, 5, 1, 0, tzinfo=UTC))
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2


class TestKeyPrefix:
    async def test_custom_key_prefix(
        self,
        redis_client: Redis,
        clock: FakeClock,
    ) -> None:
        counter = RedisDauCounter(client=redis_client, clock=clock, key_prefix="custom-dau")
        await counter.record_active(tg_user_id=111)
        assert await redis_client.zcard("custom-dau:2026-05-04") == 1
        # Default-prefix не задет.
        assert await redis_client.exists("dau:2026-05-04") == 0


class TestAtomicity:
    async def test_concurrent_record_active_same_user_yields_count_one(
        self,
        counter: RedisDauCounter,
    ) -> None:
        """asyncio.gather(10× record_active same user) ⇒ count == 1.

        ZADD-idempotency: тот же `tg_user_id` 10 раз — counter не растёт
        (ZADD на существующий member обновляет score, member-а не
        дублирует). fakeredis сохраняет атомарность pipeline-а.
        """
        await asyncio.gather(*(counter.record_active(tg_user_id=42) for _ in range(10)))
        assert await counter.current() == 1

    async def test_concurrent_record_active_different_users_yields_count_n(
        self,
        counter: RedisDauCounter,
    ) -> None:
        """asyncio.gather(50× distinct users) ⇒ count == 50.

        50 параллельных `record_active` с разными `tg_user_id` —
        все попадают в ZSET, ни одно не теряется.
        """
        await asyncio.gather(*(counter.record_active(tg_user_id=i) for i in range(50)))
        assert await counter.current() == 50
