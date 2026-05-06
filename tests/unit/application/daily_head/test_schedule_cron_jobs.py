"""Unit-тесты `ScheduleDailyHeadCronJobs` (Спринт 2.3.F.2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from pipirik_wars.application.daily_head import (
    ScheduleDailyHeadCronJobs,
    ScheduleDailyHeadCronJobsResult,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.daily_head import compute_daily_head_cron_run_at_utc
from tests.fakes import (
    FakeClanRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeUnitOfWork,
)


def _make_clan(*, clan_id: int, status: ClanStatus = ClanStatus.ACTIVE) -> Clan:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    return Clan(
        id=clan_id,
        chat_id=-1000 + clan_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=f"Clan{clan_id}"),
        status=status,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def clock() -> FakeClock:
    # 2026-05-06 03:00 UTC = 06:00 МСК того же дня (т.е. сразу после полуночи МСК).
    # Это даёт окно «сегодня осталось ~21 час», в которое попадает большая
    # часть offset-ов.
    return FakeClock(datetime(2026, 5, 6, 3, 0, tzinfo=UTC))


@pytest.fixture
def scheduler() -> FakeDelayedJobScheduler:
    return FakeDelayedJobScheduler()


@pytest.fixture
def clans() -> FakeClanRepository:
    return FakeClanRepository()


@pytest.fixture
def use_case(
    clock: FakeClock,
    scheduler: FakeDelayedJobScheduler,
    clans: FakeClanRepository,
) -> ScheduleDailyHeadCronJobs:
    return ScheduleDailyHeadCronJobs(
        uow=FakeUnitOfWork(),
        clans=clans,
        scheduler=scheduler,
        clock=clock,
    )


class TestScheduleDailyHeadCronJobs:
    @pytest.mark.asyncio
    async def test_no_active_clans_no_jobs(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
    ) -> None:
        result = await use_case.execute()

        assert result == ScheduleDailyHeadCronJobsResult(
            scheduled=(),
            skipped_past=(),
            skipped_no_id=(),
        )
        assert scheduler.scheduled_daily_head_cron == {}

    @pytest.mark.asyncio
    async def test_schedules_job_for_active_clan(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
        clock: FakeClock,
    ) -> None:
        # Найдём clan_id, у которого offset > 6 часов (>= 360 минут),
        # чтобы он точно попал «после now=06:00 МСК».
        moscow_date = clock.moscow_date()
        candidate_clan_id = next(
            cid
            for cid in range(1, 1000)
            if compute_daily_head_cron_run_at_utc(
                clan_id=cid,
                moscow_date=moscow_date,
            )
            > clock.now()
        )
        clans.rows.append(_make_clan(clan_id=candidate_clan_id))

        result = await use_case.execute()

        assert result.scheduled == (candidate_clan_id,)
        assert result.skipped_past == ()
        assert candidate_clan_id in scheduler.scheduled_daily_head_cron
        scheduled_at = scheduler.scheduled_daily_head_cron[candidate_clan_id].run_at
        expected_at = compute_daily_head_cron_run_at_utc(
            clan_id=candidate_clan_id,
            moscow_date=moscow_date,
        )
        assert scheduled_at == expected_at

    @pytest.mark.asyncio
    async def test_skips_past_offset(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
        clock: FakeClock,
    ) -> None:
        # Найдём clan_id с offset < 3 часа (< 180 мин), который уже прошёл к 06:00 МСК.
        moscow_date = clock.moscow_date()
        past_clan_id = next(
            cid
            for cid in range(1, 1000)
            if compute_daily_head_cron_run_at_utc(
                clan_id=cid,
                moscow_date=moscow_date,
            )
            <= clock.now()
        )
        clans.rows.append(_make_clan(clan_id=past_clan_id))

        result = await use_case.execute()

        assert result.scheduled == ()
        assert result.skipped_past == (past_clan_id,)
        assert past_clan_id not in scheduler.scheduled_daily_head_cron

    @pytest.mark.asyncio
    async def test_excludes_frozen_clans(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        # Frozen-клан не возвращается через `list_active`, поэтому job
        # не должен ставиться вообще.
        clans.rows.append(_make_clan(clan_id=42, status=ClanStatus.FROZEN))

        result = await use_case.execute()

        assert result.scheduled == ()
        assert result.skipped_past == ()
        assert scheduler.scheduled_daily_head_cron == {}

    @pytest.mark.asyncio
    async def test_handles_mixed_active_and_frozen(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
        clock: FakeClock,
    ) -> None:
        moscow_date = clock.moscow_date()
        # Активный клан с будущим offset-ом
        future_clan_id = next(
            cid
            for cid in range(1, 1000)
            if compute_daily_head_cron_run_at_utc(
                clan_id=cid,
                moscow_date=moscow_date,
            )
            > clock.now()
        )
        clans.rows.append(_make_clan(clan_id=future_clan_id))
        clans.rows.append(_make_clan(clan_id=999, status=ClanStatus.FROZEN))

        result = await use_case.execute()

        assert result.scheduled == (future_clan_id,)
        assert result.skipped_past == ()
        assert list(scheduler.scheduled_daily_head_cron.keys()) == [future_clan_id]

    @pytest.mark.asyncio
    async def test_idempotent_replays(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
        clock: FakeClock,
    ) -> None:
        # Два прогона use-case-а на одинаковом состоянии (бутстрэп +
        # midnight reschedule в один и тот же момент): результат идентичен,
        # последний `schedule_*` перезаписывает первый.
        moscow_date = clock.moscow_date()
        future_clan_id = next(
            cid
            for cid in range(1, 1000)
            if compute_daily_head_cron_run_at_utc(
                clan_id=cid,
                moscow_date=moscow_date,
            )
            > clock.now()
        )
        clans.rows.append(_make_clan(clan_id=future_clan_id))

        first = await use_case.execute()
        second = await use_case.execute()

        assert first == second
        # Один job на один clan_id — Fake перезаписывает.
        assert len(scheduler.scheduled_daily_head_cron) == 1

    @pytest.mark.asyncio
    async def test_run_at_uses_current_moscow_date(
        self,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        # Движение clock-а на следующие сутки → run_at тоже сдвигается.
        clock_today = FakeClock(datetime(2026, 5, 6, 3, 0, tzinfo=UTC))
        clock_tomorrow = FakeClock(datetime(2026, 5, 7, 3, 0, tzinfo=UTC))

        # Найти clan_id, который запланируется в обоих днях
        # (т.е. offset > 6h в обе даты — лень итерировать, возьмём
        # большой набор кандидатов).
        active_clan_ids = list(range(1, 200))
        for cid in active_clan_ids:
            clans.rows.append(_make_clan(clan_id=cid))

        for clock_, expected_date in [
            (clock_today, date(2026, 5, 6)),
            (clock_tomorrow, date(2026, 5, 7)),
        ]:
            scheduler_local = FakeDelayedJobScheduler()
            uc = ScheduleDailyHeadCronJobs(
                uow=FakeUnitOfWork(),
                clans=clans,
                scheduler=scheduler_local,
                clock=clock_,
            )
            await uc.execute()
            for clan_id, job in scheduler_local.scheduled_daily_head_cron.items():
                expected = compute_daily_head_cron_run_at_utc(
                    clan_id=clan_id,
                    moscow_date=expected_date,
                )
                assert job.run_at == expected

    @pytest.mark.asyncio
    async def test_skips_clan_without_id(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        # Защита от мусорной строки. `list_active` так возвращать
        # не должен, но контракт безопасный.
        garbage = replace(_make_clan(clan_id=42), id=None)
        clans.rows.append(garbage)

        result = await use_case.execute()

        assert result.scheduled == ()
        # status=ACTIVE → list_active его вернёт, мы skip-нем.
        assert result.skipped_no_id == (0,)
        assert scheduler.scheduled_daily_head_cron == {}

    @pytest.mark.asyncio
    async def test_uses_all_active_clans_in_one_pass(
        self,
        use_case: ScheduleDailyHeadCronJobs,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
        clock: FakeClock,
    ) -> None:
        # 5 активных клана с разными clan_id → все попадут в результат
        # (часть в scheduled, часть в skipped_past — зависит от offset-ов).
        for cid in (1, 2, 3, 42, 999):
            clans.rows.append(_make_clan(clan_id=cid))

        result = await use_case.execute()

        total = len(result.scheduled) + len(result.skipped_past) + len(result.skipped_no_id)
        assert total == 5

    @pytest.mark.asyncio
    async def test_at_exact_run_at_skipped(
        self,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        # Если now == run_at, мы корректно идём в skipped_past
        # (run_at <= now, неравенство нестрогое).
        moscow_date = date(2026, 5, 6)
        clan_id = 42
        run_at = compute_daily_head_cron_run_at_utc(
            clan_id=clan_id,
            moscow_date=moscow_date,
        )
        clock = FakeClock(run_at)
        clans.rows.append(_make_clan(clan_id=clan_id))
        uc = ScheduleDailyHeadCronJobs(
            uow=FakeUnitOfWork(),
            clans=clans,
            scheduler=scheduler,
            clock=clock,
        )
        result = await uc.execute()
        assert result.skipped_past == (clan_id,)
        assert scheduler.scheduled_daily_head_cron == {}

    @pytest.mark.asyncio
    async def test_just_after_run_at_skipped(
        self,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        moscow_date = date(2026, 5, 6)
        clan_id = 42
        run_at = compute_daily_head_cron_run_at_utc(
            clan_id=clan_id,
            moscow_date=moscow_date,
        )
        clock = FakeClock(run_at + timedelta(seconds=1))
        clans.rows.append(_make_clan(clan_id=clan_id))
        uc = ScheduleDailyHeadCronJobs(
            uow=FakeUnitOfWork(),
            clans=clans,
            scheduler=scheduler,
            clock=clock,
        )
        result = await uc.execute()
        assert result.skipped_past == (clan_id,)

    @pytest.mark.asyncio
    async def test_just_before_run_at_scheduled(
        self,
        scheduler: FakeDelayedJobScheduler,
        clans: FakeClanRepository,
    ) -> None:
        moscow_date = date(2026, 5, 6)
        clan_id = 42
        run_at = compute_daily_head_cron_run_at_utc(
            clan_id=clan_id,
            moscow_date=moscow_date,
        )
        clock = FakeClock(run_at - timedelta(seconds=1))
        clans.rows.append(_make_clan(clan_id=clan_id))
        uc = ScheduleDailyHeadCronJobs(
            uow=FakeUnitOfWork(),
            clans=clans,
            scheduler=scheduler,
            clock=clock,
        )
        result = await uc.execute()
        assert result.scheduled == (clan_id,)
        assert scheduler.scheduled_daily_head_cron[clan_id].run_at == run_at
