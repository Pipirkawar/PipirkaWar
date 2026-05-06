"""Unit-тесты `APSchedulerDelayedJobScheduler` (Спринт 1.3.C).

Покрытие:
- `schedule_finish_forest_run` добавляет job-у в APScheduler с тем
  же `id` (вычисляемым по `run_id`);
- повторный `schedule_*` с тем же `run_id` перезаписывает job-у
  (idempotency через `replace_existing=True`);
- `cancel_finish_forest_run` удаляет job-у;
- `cancel_finish_forest_run` для несуществующей job-ы — NO-OP;
- `start` / `shutdown` идемпотентны (повторные вызовы не падают);
- `_run_finish_job` глотает доменные ошибки (job-у пометит «прошедшей»),
  но логирует.

Сам callback на job-у (через `AsyncIOScheduler.start()` + ожидание)
гонять смысла нет — это уже зона APScheduler-а самого. Покрытие
callback-а — через прямой вызов `_run_finish_job`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pipirik_wars.application.daily_head import (
    RunDailyHeadCron,
    ScheduleDailyHeadCronJobs,
)
from pipirik_wars.application.dto.inputs import FinishForestRunInput
from pipirik_wars.application.forest import (
    FinishForestRun,
    ForestRunFinished,
    IForestFinishNotifier,
)
from pipirik_wars.application.pvp import ForceResolveMassDuel, ResolveAfkRound
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunNotFoundError,
    ForestRunStatus,
    NoDrop,
)
from pipirik_wars.domain.player import Player, PlayerNotFoundError, Username
from pipirik_wars.infrastructure.scheduler import APSchedulerDelayedJobScheduler

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@dataclass
class _FakeFinishUseCase:
    """Минимальный stub для `FinishForestRun`-факта вызова."""

    calls: list[FinishForestRunInput] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def execute(self, input_dto: FinishForestRunInput) -> ForestRunFinished:
        self.calls.append(input_dto)
        if self.raise_exc is not None:
            raise self.raise_exc
        run = ForestRun(
            id=input_dto.run_id,
            player_id=1,
            status=ForestRunStatus.FINISHED,
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
            branch_name="normal",
            length_delta_cm=3,
            drop=NoDrop(),
            finished_at=_NOW,
        )
        player = Player.new(tg_id=1, username=Username(value="alice"), now=_NOW)
        return ForestRunFinished(
            run=run,
            player_before=player,
            player_after=player,
            granted_title=False,
            granted_name=False,
            was_already_finished=False,
        )


def _build_adapter(
    *,
    fake: _FakeFinishUseCase,
    aps: AsyncIOScheduler | None = None,
) -> APSchedulerDelayedJobScheduler:
    return APSchedulerDelayedJobScheduler(
        scheduler=aps or AsyncIOScheduler(),
        finish_factory=lambda: cast(FinishForestRun, fake),
    )


class TestSchedule:
    @pytest.mark.asyncio
    async def test_schedule_adds_job_with_run_id(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_finish_forest_run(
                run_id=42,
                run_at=_NOW + timedelta(days=365),  # далеко в будущем — не сработает
            )

            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "forest_run_finish:42"
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_schedule_replaces_existing_job(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            first_at = _NOW + timedelta(days=365)
            second_at = _NOW + timedelta(days=730)
            await adapter.schedule_finish_forest_run(run_id=42, run_at=first_at)
            await adapter.schedule_finish_forest_run(run_id=42, run_at=second_at)

            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].next_run_time.replace(tzinfo=UTC) == second_at
        finally:
            adapter.shutdown(wait=False)


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_removes_job(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_finish_forest_run(
                run_id=7,
                run_at=_NOW + timedelta(days=365),
            )
            assert len(adapter._scheduler.get_jobs()) == 1

            await adapter.cancel_finish_forest_run(run_id=7)

            assert adapter._scheduler.get_jobs() == []
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_missing_is_noop(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            # Никакой job-ы нет; cancel должен молча выйти.
            await adapter.cancel_finish_forest_run(run_id=99)
        finally:
            adapter.shutdown(wait=False)


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_shutdown_idempotent(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        adapter.start()  # повторный — без падения
        adapter.shutdown(wait=False)
        adapter.shutdown(wait=False)  # повторный — без падения


class TestFinishCallback:
    @pytest.mark.asyncio
    async def test_callback_invokes_use_case(self) -> None:
        fake = _FakeFinishUseCase()
        adapter = _build_adapter(fake=fake)

        await adapter._run_finish_job(run_id=11)

        assert fake.calls == [FinishForestRunInput(run_id=11)]

    @pytest.mark.asyncio
    async def test_callback_swallows_forest_run_not_found(self) -> None:
        fake = _FakeFinishUseCase(raise_exc=ForestRunNotFoundError(run_id=11))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            logger=logger,
        )

        await adapter._run_finish_job(run_id=11)

        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_callback_swallows_player_not_found(self) -> None:
        fake = _FakeFinishUseCase(raise_exc=PlayerNotFoundError(tg_id=1))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            logger=logger,
        )

        await adapter._run_finish_job(run_id=11)

        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_callback_swallows_unexpected_error(self) -> None:
        fake = _FakeFinishUseCase(raise_exc=RuntimeError("kaboom"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            logger=logger,
        )

        await adapter._run_finish_job(run_id=11)

        assert logger.exception.called

    @pytest.mark.asyncio
    async def test_uses_default_logger_when_not_provided(self) -> None:
        fake = _FakeFinishUseCase()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
        )
        # Дефолтный logger подхватился, инстанс не None.
        assert adapter._logger is not None
        # Колбэк продолжает работать.
        await adapter._run_finish_job(run_id=1)
        assert fake.calls == [FinishForestRunInput(run_id=1)]


def test_real_finish_factory_signature() -> None:
    """Сигнатура factory-аргумента совместима с production-фабрикой
    `lambda: container.finish_forest_run`. Это обычный callable;
    реальный typecheck обеспечивает mypy на `bot/main.py`.
    """
    fake = _FakeFinishUseCase()

    def factory() -> FinishForestRun:
        return cast(FinishForestRun, fake)

    actual = factory()
    assert actual is cast(FinishForestRun, fake)


@dataclass
class _FakeNotifier(IForestFinishNotifier):
    """Stub-нотификатор: считает, сколько раз был вызван и с чем."""

    calls: list[ForestRunFinished] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def notify(self, result: ForestRunFinished) -> None:
        self.calls.append(result)
        if self.raise_exc is not None:
            raise self.raise_exc


class TestNotifierIntegration:
    @pytest.mark.asyncio
    async def test_notifier_called_after_finish(self) -> None:
        fake = _FakeFinishUseCase()
        notifier = _FakeNotifier()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            notifier=notifier,
        )

        await adapter._run_finish_job(run_id=11)

        assert len(notifier.calls) == 1
        assert notifier.calls[0].run.id == 11

    @pytest.mark.asyncio
    async def test_notifier_not_called_on_domain_error(self) -> None:
        fake = _FakeFinishUseCase(raise_exc=ForestRunNotFoundError(run_id=11))
        notifier = _FakeNotifier()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            notifier=notifier,
            logger=MagicMock(spec=logging.Logger),
        )

        await adapter._run_finish_job(run_id=11)

        assert notifier.calls == []

    @pytest.mark.asyncio
    async def test_notifier_error_is_swallowed(self) -> None:
        fake = _FakeFinishUseCase()
        notifier = _FakeNotifier(raise_exc=RuntimeError("network down"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
            notifier=notifier,
            logger=logger,
        )

        # Не должно бросать наружу — APScheduler не должен пометить job-у failed
        # из-за упавшего нотификатора.
        await adapter._run_finish_job(run_id=11)

        assert logger.exception.called

    @pytest.mark.asyncio
    async def test_no_notifier_is_optional(self) -> None:
        """Без `notifier` (старая сигнатура) работает по-прежнему."""
        fake = _FakeFinishUseCase()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, fake),
        )

        await adapter._run_finish_job(run_id=11)

        assert fake.calls == [FinishForestRunInput(run_id=11)]


@dataclass
class _FakeAfkUseCase:
    """Stub `ResolveAfkRound`-use-case-а для тестов callback-а 2.1.G."""

    calls: list[tuple[int, int]] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def execute(self, input_dto):  # type: ignore[no-untyped-def]
        self.calls.append((input_dto.duel_id, input_dto.round_num))
        if self.raise_exc is not None:
            raise self.raise_exc


class TestRoundAfkSchedule:
    """2.1.G: schedule/cancel `pvp_round_afk:{duel_id}:{round_num}`-job."""

    @pytest.mark.asyncio
    async def test_schedule_uses_per_round_id(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_round_afk_resolution(
                duel_id=42,
                round_num=2,
                run_at=_NOW + timedelta(days=365),
            )
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "pvp_round_afk:42:2"
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_schedule_replaces_same_round(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            first_at = _NOW + timedelta(days=365)
            second_at = _NOW + timedelta(days=730)
            await adapter.schedule_round_afk_resolution(duel_id=42, round_num=1, run_at=first_at)
            await adapter.schedule_round_afk_resolution(duel_id=42, round_num=1, run_at=second_at)
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].next_run_time.replace(tzinfo=UTC) == second_at
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_schedule_distinct_rounds_keep_separate_jobs(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_round_afk_resolution(
                duel_id=42, round_num=1, run_at=_NOW + timedelta(days=365)
            )
            await adapter.schedule_round_afk_resolution(
                duel_id=42, round_num=2, run_at=_NOW + timedelta(days=365)
            )
            ids = sorted(j.id for j in adapter._scheduler.get_jobs())
            assert ids == ["pvp_round_afk:42:1", "pvp_round_afk:42:2"]
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_removes_specific_round(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_round_afk_resolution(
                duel_id=42, round_num=1, run_at=_NOW + timedelta(days=365)
            )
            await adapter.schedule_round_afk_resolution(
                duel_id=42, round_num=2, run_at=_NOW + timedelta(days=365)
            )
            await adapter.cancel_round_afk_resolution(duel_id=42, round_num=1)
            ids = sorted(j.id for j in adapter._scheduler.get_jobs())
            assert ids == ["pvp_round_afk:42:2"]
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_missing_is_noop(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.cancel_round_afk_resolution(duel_id=999, round_num=1)
            assert adapter._scheduler.get_jobs() == []
        finally:
            adapter.shutdown(wait=False)


class TestRoundAfkCallback:
    """`_run_round_afk_job` callback (2.1.G)."""

    @pytest.mark.asyncio
    async def test_callback_invokes_use_case(self) -> None:
        fake = _FakeAfkUseCase()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            afk_resolution_factory=lambda: cast(ResolveAfkRound, fake),
        )
        await adapter._run_round_afk_job(duel_id=42, round_num=2)
        assert fake.calls == [(42, 2)]

    @pytest.mark.asyncio
    async def test_callback_logs_when_factory_missing(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            logger=logger,
        )
        await adapter._run_round_afk_job(duel_id=42, round_num=1)
        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_callback_swallows_unexpected_error(self) -> None:
        fake = _FakeAfkUseCase(raise_exc=RuntimeError("kaboom"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            afk_resolution_factory=lambda: cast(ResolveAfkRound, fake),
            logger=logger,
        )
        await adapter._run_round_afk_job(duel_id=42, round_num=1)
        assert logger.exception.called


@dataclass
class _FakeMassDuelAfkUseCase:
    """Stub `ForceResolveMassDuel`-use-case-а для тестов callback-а 2.2.F."""

    calls: list[int] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def execute(self, input_dto):  # type: ignore[no-untyped-def]
        self.calls.append(input_dto.duel_id)
        if self.raise_exc is not None:
            raise self.raise_exc


class TestMassDuelAfkSchedule:
    """2.2.F: schedule/cancel `pvp_mass_duel_afk:{duel_id}`-job."""

    @pytest.mark.asyncio
    async def test_schedule_uses_per_duel_id(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_mass_duel_afk_resolution(
                duel_id=42,
                run_at=_NOW + timedelta(days=365),
            )
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "pvp_mass_duel_afk:42"
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_schedule_replace_existing(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            first_at = _NOW + timedelta(days=365)
            second_at = _NOW + timedelta(days=400)
            await adapter.schedule_mass_duel_afk_resolution(duel_id=42, run_at=first_at)
            await adapter.schedule_mass_duel_afk_resolution(duel_id=42, run_at=second_at)
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].next_run_time == second_at
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_removes_only_target(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_mass_duel_afk_resolution(
                duel_id=42, run_at=_NOW + timedelta(days=365)
            )
            await adapter.schedule_mass_duel_afk_resolution(
                duel_id=43, run_at=_NOW + timedelta(days=365)
            )
            await adapter.cancel_mass_duel_afk_resolution(duel_id=42)
            ids = sorted(j.id for j in adapter._scheduler.get_jobs())
            assert ids == ["pvp_mass_duel_afk:43"]
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_missing_is_noop(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.cancel_mass_duel_afk_resolution(duel_id=999)
        finally:
            adapter.shutdown(wait=False)


class TestMassDuelAfkCallback:
    """`_run_mass_duel_afk_job` callback (2.2.F)."""

    @pytest.mark.asyncio
    async def test_callback_invokes_use_case(self) -> None:
        fake = _FakeMassDuelAfkUseCase()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            mass_duel_afk_factory=lambda: cast(ForceResolveMassDuel, fake),
        )
        await adapter._run_mass_duel_afk_job(duel_id=42)
        assert fake.calls == [42]

    @pytest.mark.asyncio
    async def test_callback_logs_when_factory_missing(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            logger=logger,
        )
        await adapter._run_mass_duel_afk_job(duel_id=42)
        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_callback_swallows_unexpected_error(self) -> None:
        fake = _FakeMassDuelAfkUseCase(raise_exc=RuntimeError("kaboom"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            mass_duel_afk_factory=lambda: cast(ForceResolveMassDuel, fake),
            logger=logger,
        )
        await adapter._run_mass_duel_afk_job(duel_id=42)
        assert logger.exception.called


@dataclass
class _FakeDailyHeadCronUseCase:
    """Stub `RunDailyHeadCron`-use-case-а для тестов callback-а 2.3.F.2."""

    calls: list[int] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def execute(self, input_dto):  # type: ignore[no-untyped-def]
        self.calls.append(input_dto.clan_id)
        if self.raise_exc is not None:
            raise self.raise_exc


class TestDailyHeadCronSchedule:
    """2.3.F.2: schedule/cancel `daily_head_cron:{clan_id}`-job."""

    @pytest.mark.asyncio
    async def test_schedule_uses_per_clan_id(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_daily_head_cron(
                clan_id=42,
                run_at=_NOW + timedelta(days=365),
            )
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "daily_head_cron:42"
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_schedule_replace_existing(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            first_at = _NOW + timedelta(days=365)
            second_at = _NOW + timedelta(days=400)
            await adapter.schedule_daily_head_cron(clan_id=42, run_at=first_at)
            await adapter.schedule_daily_head_cron(clan_id=42, run_at=second_at)
            jobs = adapter._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].next_run_time == second_at
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_removes_only_target(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.schedule_daily_head_cron(clan_id=42, run_at=_NOW + timedelta(days=365))
            await adapter.schedule_daily_head_cron(clan_id=43, run_at=_NOW + timedelta(days=365))
            await adapter.cancel_daily_head_cron(clan_id=42)
            ids = sorted(j.id for j in adapter._scheduler.get_jobs())
            assert ids == ["daily_head_cron:43"]
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_cancel_missing_is_noop(self) -> None:
        adapter = _build_adapter(fake=_FakeFinishUseCase())
        adapter.start()
        try:
            await adapter.cancel_daily_head_cron(clan_id=999)
        finally:
            adapter.shutdown(wait=False)


class TestDailyHeadCronCallback:
    """`_run_daily_head_cron_job` callback (2.3.F.2)."""

    @pytest.mark.asyncio
    async def test_callback_invokes_use_case(self) -> None:
        fake = _FakeDailyHeadCronUseCase()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            daily_head_cron_factory=lambda: cast(RunDailyHeadCron, fake),
        )
        await adapter._run_daily_head_cron_job(clan_id=42)
        assert fake.calls == [42]

    @pytest.mark.asyncio
    async def test_callback_logs_when_factory_missing(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            logger=logger,
        )
        await adapter._run_daily_head_cron_job(clan_id=42)
        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_callback_swallows_unexpected_error(self) -> None:
        fake = _FakeDailyHeadCronUseCase(raise_exc=RuntimeError("kaboom"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            daily_head_cron_factory=lambda: cast(RunDailyHeadCron, fake),
            logger=logger,
        )
        await adapter._run_daily_head_cron_job(clan_id=42)
        assert logger.exception.called


@dataclass
class _FakeScheduleDailyHeadCronJobs:
    """Stub `ScheduleDailyHeadCronJobs`-use-case-а для тестов 2.3.F.2 reschedule."""

    calls: int = 0
    raise_exc: BaseException | None = None

    async def execute(self):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc


class TestDailyHeadRescheduleCron:
    """`schedule_daily_head_reschedule_cron` + `_run_daily_head_reschedule_job`
    (2.3.F.2). Это ежедневный cron `00:01 МСК`, который зовёт
    `ScheduleDailyHeadCronJobs.execute()` для перепланирования
    per-clan job-ов на новые сутки.
    """

    @pytest.mark.asyncio
    async def test_callback_invokes_use_case(self) -> None:
        fake = _FakeScheduleDailyHeadCronJobs()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            daily_reschedule_factory=lambda: cast(ScheduleDailyHeadCronJobs, fake),
        )
        await adapter._run_daily_head_reschedule_job()
        assert fake.calls == 1

    @pytest.mark.asyncio
    async def test_callback_swallows_unexpected_error(self) -> None:
        fake = _FakeScheduleDailyHeadCronJobs(raise_exc=RuntimeError("kaboom"))
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            daily_reschedule_factory=lambda: cast(ScheduleDailyHeadCronJobs, fake),
            logger=logger,
        )
        await adapter._run_daily_head_reschedule_job()
        assert logger.exception.called

    @pytest.mark.asyncio
    async def test_callback_no_factory_no_op(self) -> None:
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
        )
        # Не должно бросить
        await adapter._run_daily_head_reschedule_job()

    @pytest.mark.asyncio
    async def test_register_cron_uses_msk_timezone_and_replace_existing(self) -> None:
        fake = _FakeScheduleDailyHeadCronJobs()
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            daily_reschedule_factory=lambda: cast(ScheduleDailyHeadCronJobs, fake),
        )
        adapter.start()
        try:
            # Идемпотентно: два вызова — один job в job-store
            adapter.schedule_daily_head_reschedule_cron()
            adapter.schedule_daily_head_reschedule_cron()
            jobs = [
                j for j in adapter._scheduler.get_jobs() if j.id == "daily_head_reschedule_cron"
            ]
            assert len(jobs) == 1
            # Триггер — CronTrigger с минутой 1 / часом 0 в Europe/Moscow.
            trigger = jobs[0].trigger
            assert hasattr(trigger, "fields")
            field_map = {f.name: str(f) for f in trigger.fields}
            assert field_map["minute"] == "1"
            assert field_map["hour"] == "0"
            assert "Moscow" in str(trigger.timezone)
        finally:
            adapter.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_register_cron_no_factory_logs_warning(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        adapter = APSchedulerDelayedJobScheduler(
            scheduler=AsyncIOScheduler(),
            finish_factory=lambda: cast(FinishForestRun, _FakeFinishUseCase()),
            logger=logger,
        )
        adapter.schedule_daily_head_reschedule_cron()
        assert logger.warning.called
