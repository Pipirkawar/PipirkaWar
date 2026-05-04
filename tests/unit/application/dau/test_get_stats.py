"""Юнит-тесты `GetDauStats` (Спринт 1.2.3)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.dau import DauStats, GetDauStats
from pipirik_wars.infrastructure.dau import InMemoryDauCounter, InMemoryDauLimit
from tests.fakes import FakeClock


@pytest.mark.asyncio
async def test_get_stats_returns_zero_for_empty_counter() -> None:
    clock = FakeClock()
    counter = InMemoryDauCounter(clock=clock)
    limit = InMemoryDauLimit(initial=200)
    use_case = GetDauStats(counter=counter, limit=limit)

    stats = await use_case.execute()
    assert isinstance(stats, DauStats)
    assert stats.current == 0
    assert stats.max_dau == 200
    assert stats.is_full is False
    assert stats.utilization_percent == 0


@pytest.mark.asyncio
async def test_get_stats_after_recording_activity() -> None:
    clock = FakeClock()
    counter = InMemoryDauCounter(clock=clock)
    limit = InMemoryDauLimit(initial=10)
    use_case = GetDauStats(counter=counter, limit=limit)

    for tg_id in (1, 2, 3):
        await counter.record_active(tg_user_id=tg_id)

    stats = await use_case.execute()
    assert stats.current == 3
    assert stats.max_dau == 10
    assert stats.is_full is False
    assert stats.utilization_percent == 30


@pytest.mark.asyncio
async def test_get_stats_at_capacity_marks_full() -> None:
    clock = FakeClock()
    counter = InMemoryDauCounter(clock=clock)
    limit = InMemoryDauLimit(initial=3)
    use_case = GetDauStats(counter=counter, limit=limit)

    for tg_id in (1, 2, 3):
        await counter.record_active(tg_user_id=tg_id)

    stats = await use_case.execute()
    assert stats.current == 3
    assert stats.is_full is True
    assert stats.utilization_percent == 100


@pytest.mark.asyncio
async def test_get_stats_above_capacity() -> None:
    # Технически возможно: лимит снизили после того, как DAU
    # перевалил за новое значение. Не должны падать; `is_full = True`.
    clock = FakeClock()
    counter = InMemoryDauCounter(clock=clock)
    limit = InMemoryDauLimit(initial=10)
    use_case = GetDauStats(counter=counter, limit=limit)

    for tg_id in range(15):
        await counter.record_active(tg_user_id=tg_id)
    # Снижаем лимит ниже текущего DAU.
    await limit.set(max_dau=5)

    stats = await use_case.execute()
    assert stats.current == 15
    assert stats.max_dau == 5
    assert stats.is_full is True
    assert stats.utilization_percent == 300


@pytest.mark.asyncio
async def test_get_stats_reflects_runtime_limit_change() -> None:
    clock = FakeClock()
    counter = InMemoryDauCounter(clock=clock)
    limit = InMemoryDauLimit(initial=200)
    use_case = GetDauStats(counter=counter, limit=limit)

    stats1 = await use_case.execute()
    assert stats1.max_dau == 200

    await limit.set(max_dau=1000)
    stats2 = await use_case.execute()
    assert stats2.max_dau == 1000


def test_dau_stats_utilization_handles_zero_max() -> None:
    # `IDauLimit` всегда возвращает >= 1, но проверим property отдельно
    # (paranoia против ZeroDivisionError).
    stats = DauStats(current=5, max_dau=0)
    assert stats.utilization_percent == 0
    # `is_full` тоже не падает.
    assert stats.is_full is True  # 5 >= 0


def test_dau_stats_is_frozen() -> None:
    stats = DauStats(current=10, max_dau=100)
    with pytest.raises((AttributeError, TypeError)):
        stats.current = 20
