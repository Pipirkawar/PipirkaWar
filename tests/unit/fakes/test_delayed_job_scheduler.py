"""Тесты `FakeDelayedJobScheduler`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeDelayedJobScheduler, ScheduledFinish

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


class TestFakeDelayedJobScheduler:
    @pytest.mark.asyncio
    async def test_schedule_records_entry(self) -> None:
        scheduler = FakeDelayedJobScheduler()
        run_at = _NOW + timedelta(minutes=10)

        await scheduler.schedule_finish_forest_run(run_id=42, run_at=run_at)

        assert scheduler.scheduled[42] == ScheduledFinish(run_id=42, run_at=run_at)

    @pytest.mark.asyncio
    async def test_schedule_overwrites_existing_entry(self) -> None:
        scheduler = FakeDelayedJobScheduler()
        first = _NOW + timedelta(minutes=10)
        second = _NOW + timedelta(minutes=20)

        await scheduler.schedule_finish_forest_run(run_id=42, run_at=first)
        await scheduler.schedule_finish_forest_run(run_id=42, run_at=second)

        assert scheduler.scheduled[42].run_at == second
        assert len(scheduler.scheduled) == 1

    @pytest.mark.asyncio
    async def test_cancel_removes_entry_and_records_call(self) -> None:
        scheduler = FakeDelayedJobScheduler()
        await scheduler.schedule_finish_forest_run(
            run_id=7,
            run_at=_NOW + timedelta(minutes=10),
        )

        await scheduler.cancel_finish_forest_run(run_id=7)

        assert 7 not in scheduler.scheduled
        assert scheduler.cancelled == [7]

    @pytest.mark.asyncio
    async def test_cancel_missing_is_noop(self) -> None:
        scheduler = FakeDelayedJobScheduler()
        await scheduler.cancel_finish_forest_run(run_id=999)

        assert scheduler.cancelled == [999]
        assert scheduler.scheduled == {}
