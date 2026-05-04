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

from pipirik_wars.application.dto.inputs import FinishForestRunInput
from pipirik_wars.application.forest import (
    FinishForestRun,
    ForestRunFinished,
    IForestFinishNotifier,
)
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
