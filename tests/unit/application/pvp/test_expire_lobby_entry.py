"""Unit-тесты `ExpireLobbyEntry` (Спринт 2.1.F.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import ExpireLobbyEntryInput
from pipirik_wars.application.pvp import (
    ExpireLobbyEntry,
    LobbyEntryExpirationSkipped,
    LobbyEntryExpired,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import Duel, DuelMode, DuelState
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=10)


def _build() -> tuple[
    ExpireLobbyEntry,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    lobby = FakeGlobalLobbyRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    use_case = ExpireLobbyEntry(
        uow=uow,
        duels=duels,
        lobby=lobby,
        locks=locks,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, lobby, lock_repo, audit, uow


async def _seed_global_pending(
    duels: FakeDuelRepository,
    *,
    challenger_id: int,
) -> Duel:
    pending = Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=None,
        mode=DuelMode.GLOBAL_ONLY,
        hit_pct=10,
        expected_rounds=3,
        now=_EARLIER,
    )
    return await duels.add(pending)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_expires_pending_global_duel(self) -> None:
        use_case, players, duels, lobby, lock_repo, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_global_pending(duels, challenger_id=challenger.id)
        assert pending.id is not None
        await lobby.enqueue(duel_id=pending.id, enqueued_at=_EARLIER)
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=challenger.id,
            reason=LockReason.PVP,
            now=_EARLIER,
            expires_at=_NOW + timedelta(minutes=20),
        )

        result = await use_case.execute(ExpireLobbyEntryInput(duel_id=pending.id))

        assert isinstance(result, LobbyEntryExpired)
        assert result.duel.state is DuelState.CANCELLED
        assert result.duel.cancelled_at == _NOW
        assert lobby.rows == []
        assert ("player", challenger.id) not in lock_repo.locks
        actions = [e.action for e in audit.entries]
        assert AuditAction.PVP_LOBBY_EXPIRED in actions
        assert AuditAction.PVP_DUEL_CANCELLED in actions
        assert uow.commits == 1


class TestSkipScenarios:
    @pytest.mark.asyncio
    async def test_noop_when_not_in_lobby(self) -> None:
        use_case, players, duels, lobby, _lr, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_global_pending(duels, challenger_id=challenger.id)
        assert pending.id is not None
        # НЕ ставим в лобби

        result = await use_case.execute(ExpireLobbyEntryInput(duel_id=pending.id))

        assert isinstance(result, LobbyEntryExpirationSkipped)
        assert result.reason == "not_in_lobby"
        assert audit.entries == []
        assert uow.commits == 1
        # дуэль осталась в PENDING_ACCEPT
        reloaded = await duels.get_by_id(duel_id=pending.id)
        assert reloaded is not None
        assert reloaded.state is DuelState.PENDING_ACCEPT

    @pytest.mark.asyncio
    async def test_noop_when_duel_disappeared(self) -> None:
        use_case, _p, _d, lobby, _lr, audit, _u = _build()
        # запись в лобби есть, но дуэли в БД нет (CASCADE-удалёние)
        await lobby.enqueue(duel_id=42, enqueued_at=_EARLIER)
        result = await use_case.execute(ExpireLobbyEntryInput(duel_id=42))
        assert isinstance(result, LobbyEntryExpirationSkipped)
        assert result.reason == "not_found"
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_noop_when_race_with_accept(self) -> None:
        """Дуэль в лобби, но кто-то уже принял (state IN_PROGRESS).

        Должны убрать запись из лобби и вернуть skipped.
        """
        use_case, players, duels, lobby, _lr, audit, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_global_pending(duels, challenger_id=challenger.id)
        assert pending.id is not None
        await lobby.enqueue(duel_id=pending.id, enqueued_at=_EARLIER)
        # эмулируем race: accept перевёл в IN_PROGRESS, но expire job сработал
        accepted = pending.accept(
            accepter_id=challenged.id,
            p1_length_cm=challenger.length.cm,
            p2_length_cm=challenged.length.cm,
            now=_EARLIER + timedelta(seconds=30),
        )
        await duels.save(accepted)

        result = await use_case.execute(ExpireLobbyEntryInput(duel_id=pending.id))

        assert isinstance(result, LobbyEntryExpirationSkipped)
        assert result.reason == "not_pending_accept"
        # запись из лобби убрана
        assert lobby.rows == []
        assert audit.entries == []
