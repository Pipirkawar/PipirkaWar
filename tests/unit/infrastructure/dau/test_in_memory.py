"""Юнит-тесты `InMemoryDauCounter` / `InMemoryDauLimit` (Спринт 1.2.B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pipirik_wars.infrastructure.dau import InMemoryDauCounter, InMemoryDauLimit
from tests.fakes import FakeClock

_MOSCOW_TZ = timezone(timedelta(hours=3))


def _msk(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=_MOSCOW_TZ).astimezone(UTC)


class TestInMemoryDauCounter:
    @pytest.mark.asyncio
    async def test_empty_counter_starts_at_zero(self) -> None:
        clock = FakeClock(_msk(2026, 5, 4))
        counter = InMemoryDauCounter(clock=clock)
        assert await counter.current() == 0

    @pytest.mark.asyncio
    async def test_record_active_counts_unique_users(self) -> None:
        clock = FakeClock(_msk(2026, 5, 4, hour=10))
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        await counter.record_active(tg_user_id=111)  # дубль — не должен счётчик увеличить
        assert await counter.current() == 2

    @pytest.mark.asyncio
    async def test_resets_on_new_moscow_day(self) -> None:
        clock = FakeClock(_msk(2026, 5, 4, hour=23))
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

        # Переход через полночь МСК (на 2 часа вперёд → 01:00 5 мая МСК).
        clock.advance(hours=2)
        assert await counter.current() == 0  # сброс

        await counter.record_active(tg_user_id=333)
        assert await counter.current() == 1

    @pytest.mark.asyncio
    async def test_no_reset_within_same_moscow_day(self) -> None:
        clock = FakeClock(_msk(2026, 5, 4, hour=1))
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)
        # 22 часа спустя — всё ещё 4 мая МСК (с 01:00 до 23:00).
        clock.advance(hours=22)
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

    @pytest.mark.asyncio
    async def test_reset_lazy_only_on_first_call_after_midnight(self) -> None:
        # Если бот «спал» через полночь и не было вызовов — set всё ещё
        # с прошлого дня в памяти. Первый вызов после полуночи МСК
        # обнуляет.
        clock = FakeClock(_msk(2026, 5, 4, hour=23))
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)

        clock.advance(days=2)  # перешли в 6 мая МСК
        # Первый вызов после большого «прыжка» сбрасывает.
        assert await counter.current() == 0

    @pytest.mark.asyncio
    async def test_record_active_after_reset_starts_fresh(self) -> None:
        clock = FakeClock(_msk(2026, 5, 4, hour=23))
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)

        clock.advance(hours=2)  # 5 мая 01:00 МСК
        await counter.record_active(tg_user_id=111)  # снова — но это «новый» день
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2

    @pytest.mark.asyncio
    async def test_uses_moscow_timezone_for_day_boundary(self) -> None:
        # 4 мая 22:00 UTC = 5 мая 01:00 МСК. Так что счётчик уже на «5-м» дне.
        utc_late = datetime(2026, 5, 4, 22, 0, tzinfo=UTC)
        clock = FakeClock(utc_late)
        counter = InMemoryDauCounter(clock=clock)
        await counter.record_active(tg_user_id=111)

        # Перешли на UTC 5 мая 01:00 = МСК 04:00 — всё ещё 5-й день МСК.
        clock.set(datetime(2026, 5, 5, 1, 0, tzinfo=UTC))
        await counter.record_active(tg_user_id=222)
        assert await counter.current() == 2  # один и тот же МСК-день


class TestInMemoryDauLimit:
    @pytest.mark.asyncio
    async def test_initial_value_returned(self) -> None:
        limit = InMemoryDauLimit(initial=500)
        assert await limit.get() == 500

    @pytest.mark.asyncio
    async def test_set_returns_previous_value(self) -> None:
        limit = InMemoryDauLimit(initial=200)
        previous = await limit.set(max_dau=1000)
        assert previous == 200
        assert await limit.get() == 1000

    @pytest.mark.asyncio
    async def test_set_to_same_value_returns_same(self) -> None:
        limit = InMemoryDauLimit(initial=500)
        previous = await limit.set(max_dau=500)
        assert previous == 500
        assert await limit.get() == 500

    @pytest.mark.asyncio
    async def test_set_zero_or_negative_rejected(self) -> None:
        limit = InMemoryDauLimit(initial=200)
        with pytest.raises(ValueError, match="max_dau must be >= 1"):
            await limit.set(max_dau=0)
        with pytest.raises(ValueError, match="max_dau must be >= 1"):
            await limit.set(max_dau=-1)
        # Состояние не изменилось.
        assert await limit.get() == 200

    def test_initial_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="initial MAX_DAU must be >= 1"):
            InMemoryDauLimit(initial=0)

    def test_initial_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="initial MAX_DAU must be >= 1"):
            InMemoryDauLimit(initial=-100)

    @pytest.mark.asyncio
    async def test_multiple_sets_in_sequence(self) -> None:
        limit = InMemoryDauLimit(initial=100)
        prev1 = await limit.set(max_dau=200)
        prev2 = await limit.set(max_dau=300)
        prev3 = await limit.set(max_dau=150)
        assert (prev1, prev2, prev3) == (100, 200, 300)
        assert await limit.get() == 150
