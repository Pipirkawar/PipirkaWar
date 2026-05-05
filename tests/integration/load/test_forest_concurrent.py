"""Мини-нагрузочный тест: 100 параллельных `/forest` (Спринт 1.4.D, ПД 1.4.7).

Цель — убедиться, что при шквале запросов:

1. **Один игрок, 100 параллельных `/forest`** → ровно ОДНА запись
   `forest_runs(IN_PROGRESS)`, остальные 99 корутин получают
   `AlreadyInForestError`. Лок `activity_locks(actor_kind='player',
   actor_id=…)` остаётся ровно одна запись. Это и есть
   acceptance ПД §1.4.7 — «100 параллельных «походов в лес» без
   потери лока».

2. **100 разных игроков, по одному `/forest` каждый** → 100 успешных
   запусков, по одной записи `forest_runs(IN_PROGRESS)` на игрока,
   100 записей в `activity_locks`. Это контрольный сценарий: сам по
   себе использует тот же путь, но без конкуренции за лок.

Каждая корутина получает собственный `SqlAlchemyUnitOfWork` от общего
`session_maker` — это имитирует прод-кейс, где у каждого aiogram-
update свой DI-контейнер транзакций. Для in-memory SQLite используем
`StaticPool` (см. `conftest.py`), чтобы все сессии видели одну БД.

Тест помечен `@pytest.mark.slow`: даже на быстрой машине занимает
секунды и не подходит для tight-loop разработки.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipirik_wars.application.dto.inputs import StartForestRunInput
from pipirik_wars.application.forest import StartForestRun
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.forest import (
    AlreadyInForestError,
    ForestRunStatus,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.db.models import (
    ActivityLockORM,
    ForestRunORM,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyActivityLockRepository,
    SqlAlchemyForestRunRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services import SqlAlchemyAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import RealRandom
from tests.fakes import FakeBalanceConfig, FakeDelayedJobScheduler
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)


def _build_use_case(uow: SqlAlchemyUnitOfWork) -> StartForestRun:
    """Свежий use-case под собственный UoW. Inputs — общие
    (`FakeBalanceConfig`, real RNG, real clock).
    """
    balance = FakeBalanceConfig(build_valid_balance())
    clock = RealClock()
    locks_repo = SqlAlchemyActivityLockRepository(uow=uow)
    return StartForestRun(
        uow=uow,
        players=SqlAlchemyPlayerRepository(uow=uow),
        runs=SqlAlchemyForestRunRepository(uow=uow, balance=balance),
        locks=ActivityLockService(repository=locks_repo, clock=clock),
        balance=balance,
        random=RealRandom(),
        audit=SqlAlchemyAuditLogger(uow=uow),
        clock=clock,
        scheduler=FakeDelayedJobScheduler(),
    )


async def _seed_player(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    tg_id: int,
) -> Player:
    seed_uow = SqlAlchemyUnitOfWork(session_maker)
    async with seed_uow:
        return await SqlAlchemyPlayerRepository(uow=seed_uow).add(
            Player.new(tg_id=tg_id, username=None, now=NOW),
        )


@pytest.mark.asyncio
@pytest.mark.slow
class TestForestConcurrentLoad:
    async def test_100_parallel_starts_for_same_player_only_one_wins(
        self,
        shared_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """ПД §1.4.7: 100 параллельных `/forest` на одного игрока —
        ровно один поход стартует, 99 уходят в `AlreadyInForestError`.
        """
        player = await _seed_player(shared_session_maker, tg_id=42)

        async def attempt() -> str:
            uow = SqlAlchemyUnitOfWork(shared_session_maker)
            use_case = _build_use_case(uow)
            try:
                await use_case.execute(StartForestRunInput(tg_id=player.tg_id))
            except AlreadyInForestError:
                return "locked"
            else:
                return "ok"

        results = await asyncio.gather(*(attempt() for _ in range(100)))

        assert results.count("ok") == 1, f"expected 1 success, got {results.count('ok')}"
        assert results.count("locked") == 99, f"expected 99 locked, got {results.count('locked')}"

        # Проверяем consistency БД: ровно 1 IN_PROGRESS-поход и 1 запись
        # в activity_locks для этого игрока.
        check_uow = SqlAlchemyUnitOfWork(shared_session_maker)
        async with check_uow:
            session = check_uow.session
            in_progress_count = await session.scalar(
                select(func.count())
                .select_from(ForestRunORM)
                .where(
                    ForestRunORM.player_id == player.id,
                    ForestRunORM.status == ForestRunStatus.IN_PROGRESS.value,
                ),
            )
            assert in_progress_count == 1
            lock_count = await session.scalar(
                select(func.count())
                .select_from(ActivityLockORM)
                .where(
                    ActivityLockORM.actor_kind == "player",
                    ActivityLockORM.actor_id == player.id,
                ),
            )
            assert lock_count == 1

    async def test_100_parallel_starts_for_different_players_all_succeed(
        self,
        shared_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """100 разных игроков по одному `/forest` каждому — все 100
        запускаются (нет ложных конфликтов на чужих локах).
        """
        players: list[Player] = await asyncio.gather(
            *(_seed_player(shared_session_maker, tg_id=1000 + i) for i in range(100)),
        )

        async def attempt(tg_id: int) -> str:
            uow = SqlAlchemyUnitOfWork(shared_session_maker)
            use_case = _build_use_case(uow)
            try:
                await use_case.execute(StartForestRunInput(tg_id=tg_id))
            except AlreadyInForestError:
                return "locked"
            else:
                return "ok"

        results = await asyncio.gather(*(attempt(p.tg_id) for p in players))
        assert results.count("ok") == 100, f"expected 100 successes, got {results.count('ok')}"

        # Проверяем: 100 IN_PROGRESS-походов и 100 локов.
        check_uow = SqlAlchemyUnitOfWork(shared_session_maker)
        async with check_uow:
            session = check_uow.session
            in_progress_count = await session.scalar(
                select(func.count())
                .select_from(ForestRunORM)
                .where(ForestRunORM.status == ForestRunStatus.IN_PROGRESS.value),
            )
            assert in_progress_count == 100
            lock_count = await session.scalar(
                select(func.count()).select_from(ActivityLockORM),
            )
            assert lock_count == 100
