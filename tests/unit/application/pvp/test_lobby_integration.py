"""Интеграция scheduler/lobby в Challenge/Accept/CancelDuel (Спринт 2.1.F.2 step 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import (
    AcceptDuelInput,
    CancelDuelInput,
    ChallengeDuelInput,
)
from pipirik_wars.application.pvp import (
    AcceptDuel,
    CancelDuel,
    ChallengeDuel,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import Duel, DuelMode, DuelState
from pipirik_wars.domain.security import LockReason
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=2)


def _build_challenge_duel() -> tuple[
    ChallengeDuel,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakeDelayedJobScheduler,
    FakeAuditLogger,
    FakeUnitOfWork,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    lobby = FakeGlobalLobbyRepository()
    scheduler = FakeDelayedJobScheduler()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = ChallengeDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        balance=balance,
        audit=audit,
        clock=clock,
        scheduler=scheduler,
        lobby=lobby,
    )
    return use_case, players, duels, lobby, scheduler, audit, uow


def _build_accept_duel() -> tuple[
    AcceptDuel,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakeDelayedJobScheduler,
    FakeAuditLogger,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    lobby = FakeGlobalLobbyRepository()
    scheduler = FakeDelayedJobScheduler()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = AcceptDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        balance=balance,
        audit=audit,
        clock=clock,
        scheduler=scheduler,
        lobby=lobby,
    )
    return use_case, players, duels, lobby, scheduler, audit


def _build_cancel_duel() -> tuple[
    CancelDuel,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakeDelayedJobScheduler,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    lobby = FakeGlobalLobbyRepository()
    scheduler = FakeDelayedJobScheduler()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    use_case = CancelDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        audit=audit,
        clock=clock,
        scheduler=scheduler,
        lobby=lobby,
    )
    return use_case, players, duels, lobby, scheduler, lock_repo


class TestChallengeDuelScheduling:
    @pytest.mark.asyncio
    async def test_chat_then_global_schedules_escalation_only(self) -> None:
        use_case, players, _d, lobby, scheduler, _a, _u = _build_challenge_duel()
        await seed_pvp_eligible_player(players, tg_id=1)
        await seed_pvp_eligible_player(players, tg_id=2, username="bob")

        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=2,
                mode="chat_then_global",
            )
        )

        assert result.duel.id is not None
        # escalation запланирована на 3 минуты вперёд
        assert result.duel.id in scheduler.scheduled_escalations
        assert scheduler.scheduled_escalations[result.duel.id].run_at == _NOW + timedelta(minutes=3)
        # лобби-expiration НЕ запланирована (мы ещё в чате)
        assert scheduler.scheduled_expirations == {}
        # в лобби пока никого
        assert lobby.rows == []

    @pytest.mark.asyncio
    async def test_global_only_enqueues_lobby_and_schedules_expiration(self) -> None:
        use_case, players, _d, lobby, scheduler, audit, _u = _build_challenge_duel()
        await seed_pvp_eligible_player(players, tg_id=1)

        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=None,
                mode="global_only",
            )
        )

        assert result.duel.id is not None
        # запись в лобби есть
        assert any(r.duel_id == result.duel.id for r in lobby.rows)
        # expiration через 10 минут
        assert result.duel.id in scheduler.scheduled_expirations
        assert scheduler.scheduled_expirations[result.duel.id].run_at == _NOW + timedelta(
            minutes=10
        )
        # escalation НЕ планируется
        assert scheduler.scheduled_escalations == {}
        # 2 audit-записи: PVP_DUEL_CREATED + PVP_LOBBY_ENQUEUED
        assert len(audit.entries) == 2

    @pytest.mark.asyncio
    async def test_chat_only_does_not_schedule_anything(self) -> None:
        use_case, players, _d, lobby, scheduler, _a, _u = _build_challenge_duel()
        await seed_pvp_eligible_player(players, tg_id=1)
        await seed_pvp_eligible_player(players, tg_id=2, username="bob")

        await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=2,
                mode="chat_only",
            )
        )

        assert scheduler.scheduled_escalations == {}
        assert scheduler.scheduled_expirations == {}
        assert lobby.rows == []


class TestAcceptDuelCleanup:
    @pytest.mark.asyncio
    async def test_chat_then_global_accept_cancels_escalation(self) -> None:
        use_case, players, duels, _l, scheduler, _a = _build_accept_duel()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await duels.add(
            Duel.create_challenge(
                challenger_id=challenger.id,
                challenged_id=accepter.id,
                mode=DuelMode.CHAT_THEN_GLOBAL,
                hit_pct=10,
                expected_rounds=3,
                now=_EARLIER,
            )
        )
        assert pending.id is not None

        await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

        assert pending.id in scheduler.cancelled_escalations
        assert pending.id not in scheduler.cancelled_expirations

    @pytest.mark.asyncio
    async def test_global_only_accept_cancels_expiration_and_removes_lobby(self) -> None:
        use_case, players, duels, lobby, scheduler, _a = _build_accept_duel()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await duels.add(
            Duel.create_challenge(
                challenger_id=challenger.id,
                challenged_id=None,
                mode=DuelMode.GLOBAL_ONLY,
                hit_pct=10,
                expected_rounds=3,
                now=_EARLIER,
            )
        )
        assert pending.id is not None
        await lobby.enqueue(duel_id=pending.id, enqueued_at=_EARLIER)

        await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

        assert pending.id in scheduler.cancelled_expirations
        assert pending.id not in scheduler.cancelled_escalations
        assert lobby.rows == []


class TestCancelDuelCleanup:
    @pytest.mark.asyncio
    async def test_chat_then_global_cancel_cancels_escalation(self) -> None:
        use_case, players, duels, _l, scheduler, lock_repo = _build_cancel_duel()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await duels.add(
            Duel.create_challenge(
                challenger_id=challenger.id,
                challenged_id=challenged.id,
                mode=DuelMode.CHAT_THEN_GLOBAL,
                hit_pct=10,
                expected_rounds=3,
                now=_EARLIER,
            )
        )
        assert pending.id is not None
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=challenger.id,
            reason=LockReason.PVP,
            now=_EARLIER,
            expires_at=_NOW + timedelta(minutes=30),
        )

        await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=1))

        assert pending.id in scheduler.cancelled_escalations
        assert pending.id not in scheduler.cancelled_expirations

    @pytest.mark.asyncio
    async def test_global_only_cancel_cancels_expiration_and_removes_lobby(self) -> None:
        use_case, players, duels, lobby, scheduler, lock_repo = _build_cancel_duel()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await duels.add(
            Duel.create_challenge(
                challenger_id=challenger.id,
                challenged_id=None,
                mode=DuelMode.GLOBAL_ONLY,
                hit_pct=10,
                expected_rounds=3,
                now=_EARLIER,
            )
        )
        assert pending.id is not None
        await lobby.enqueue(duel_id=pending.id, enqueued_at=_EARLIER)
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=challenger.id,
            reason=LockReason.PVP,
            now=_EARLIER,
            expires_at=_NOW + timedelta(minutes=30),
        )

        await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=1))

        assert pending.id in scheduler.cancelled_expirations
        assert pending.id not in scheduler.cancelled_escalations
        assert lobby.rows == []

    @pytest.mark.asyncio
    async def test_idempotent_already_cancelled_does_not_call_scheduler(self) -> None:
        use_case, players, duels, _l, scheduler, lock_repo = _build_cancel_duel()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await duels.add(
            Duel.create_challenge(
                challenger_id=challenger.id,
                challenged_id=None,
                mode=DuelMode.GLOBAL_ONLY,
                hit_pct=10,
                expected_rounds=3,
                now=_EARLIER,
            )
        )
        assert pending.id is not None
        # сразу отменяем «вручную» — без scheduler-cleanup
        cancelled = pending.cancel(now=_NOW)
        await duels.save(cancelled)

        result = await use_case.execute(
            CancelDuelInput(duel_id=pending.id, tg_id=1),
        )

        assert result.was_already_cancelled is True
        # повторная отмена не пишет ничего в scheduler
        assert scheduler.cancelled_escalations == []
        assert scheduler.cancelled_expirations == []


class TestNoSchedulerStillWorks:
    """Существующий код без подвязанного scheduler/lobby должен работать."""

    @pytest.mark.asyncio
    async def test_challenge_without_scheduler(self) -> None:
        # ChallengeDuel без scheduler/lobby — fall-through, не валится
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeDuelRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        balance = FakeBalanceConfig(build_valid_balance())
        use_case = ChallengeDuel(
            uow=uow,
            players=players,
            duels=duels,
            locks=locks,
            balance=balance,
            audit=audit,
            clock=clock,
        )
        await seed_pvp_eligible_player(players, tg_id=1)
        result = await use_case.execute(
            ChallengeDuelInput(
                challenger_tg_id=1,
                challenged_tg_id=None,
                mode="global_only",
            )
        )
        assert result.duel.state is DuelState.PENDING_ACCEPT
