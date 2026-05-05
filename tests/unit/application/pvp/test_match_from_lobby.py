"""Unit-тесты `MatchFromLobby` (Спринт 2.1.F.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import MatchFromLobbyInput
from pipirik_wars.application.pvp import (
    DuelMatched,
    EmptyLobby,
    LobbyEntryStale,
    MatchFromLobby,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelState,
    PvpRequirementsNotMetError,
)
from pipirik_wars.domain.shared.ports import AuditAction
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


def _build() -> tuple[
    MatchFromLobby,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeGlobalLobbyRepository,
    FakeActivityLockRepository,
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
    use_case = MatchFromLobby(
        uow=uow,
        players=players,
        duels=duels,
        lobby=lobby,
        locks=locks,
        scheduler=scheduler,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, lobby, lock_repo, scheduler, audit, uow


async def _seed_global_in_lobby(
    duels: FakeDuelRepository,
    lobby: FakeGlobalLobbyRepository,
    *,
    challenger_id: int,
    enqueued_at: datetime = _EARLIER,
) -> Duel:
    pending = Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=None,
        mode=DuelMode.GLOBAL_ONLY,
        hit_pct=10,
        expected_rounds=3,
        now=enqueued_at,
    )
    saved = await duels.add(pending)
    assert saved.id is not None
    await lobby.enqueue(duel_id=saved.id, enqueued_at=enqueued_at)
    return saved


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_matches_oldest_duel_in_fifo_order(self) -> None:
        use_case, players, duels, lobby, lock_repo, scheduler, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        # 2 вызова в лобби, второй позже — должен пикапнуться первый
        first = await _seed_global_in_lobby(
            duels,
            lobby,
            challenger_id=challenger.id,
            enqueued_at=_EARLIER,
        )
        challenger_b = await seed_pvp_eligible_player(players, tg_id=3, username="charlie")
        assert challenger_b.id is not None
        await _seed_global_in_lobby(
            duels,
            lobby,
            challenger_id=challenger_b.id,
            enqueued_at=_EARLIER + timedelta(minutes=1),
        )

        result = await use_case.execute(MatchFromLobbyInput(accepter_tg_id=2))

        assert isinstance(result, DuelMatched)
        assert result.duel.id == first.id
        assert result.duel.state is DuelState.IN_PROGRESS
        assert result.duel.challenged_id == accepter.id
        # лок на принимающего поставлен
        assert ("player", accepter.id) in lock_repo.locks
        # старший вызов вынут из лобби, второй остался
        assert len(lobby.rows) == 1
        assert lobby.rows[0].duel_id != first.id
        # cancel expiration job
        assert first.id in scheduler.cancelled_expirations
        # 2 audit-записи: PVP_DUEL_ACCEPTED + PVP_LOBBY_MATCHED
        actions = [e.action for e in audit.entries]
        assert AuditAction.PVP_DUEL_ACCEPTED in actions
        assert AuditAction.PVP_LOBBY_MATCHED in actions
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_returns_empty_lobby(self) -> None:
        use_case, players, _d, _l, _lr, scheduler, audit, _u = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        result = await use_case.execute(MatchFromLobbyInput(accepter_tg_id=1))
        assert isinstance(result, EmptyLobby)
        assert audit.entries == []
        assert scheduler.cancelled_expirations == []


class TestStaleScenarios:
    @pytest.mark.asyncio
    async def test_self_challenge_returns_entry_to_lobby(self) -> None:
        use_case, players, duels, lobby, _lr, scheduler, audit, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        seeded = await _seed_global_in_lobby(
            duels,
            lobby,
            challenger_id=challenger.id,
            enqueued_at=_EARLIER,
        )

        result = await use_case.execute(MatchFromLobbyInput(accepter_tg_id=1))

        assert isinstance(result, LobbyEntryStale)
        assert result.reason == "self_challenge"
        # запись возвращена в лобби
        assert any(r.duel_id == seeded.id for r in lobby.rows)
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_stale_when_duel_already_accepted(self) -> None:
        use_case, players, duels, lobby, _lr, scheduler, audit, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        accepter = await seed_pvp_eligible_player(players, tg_id=3, username="charlie")
        assert challenger.id is not None
        assert challenged.id is not None
        assert accepter.id is not None
        seeded = await _seed_global_in_lobby(
            duels,
            lobby,
            challenger_id=challenger.id,
            enqueued_at=_EARLIER,
        )
        assert seeded.id is not None
        # эмулируем race: accept перевёл в IN_PROGRESS
        accepted = seeded.accept(
            accepter_id=challenged.id,
            p1_length_cm=challenger.length.cm,
            p2_length_cm=challenged.length.cm,
            now=_EARLIER + timedelta(seconds=30),
        )
        await duels.save(accepted)

        result = await use_case.execute(MatchFromLobbyInput(accepter_tg_id=3))

        assert isinstance(result, LobbyEntryStale)
        assert result.reason == "not_pending_accept"
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_stale_when_duel_disappeared(self) -> None:
        use_case, players, _d, lobby, _lr, _s, audit, _u = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        await lobby.enqueue(duel_id=999, enqueued_at=_EARLIER)
        result = await use_case.execute(MatchFromLobbyInput(accepter_tg_id=1))
        assert isinstance(result, LobbyEntryStale)
        assert result.reason == "duel_not_found"


class TestEligibility:
    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, _p, _d, _l, _lr, _s, _a, _u = _build()
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(MatchFromLobbyInput(accepter_tg_id=999))

    @pytest.mark.asyncio
    async def test_below_pvp_requirements(self) -> None:
        use_case, players, duels, lobby, _lr, _s, _a, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        # принимающий — длина 5 см (ниже порога 20)
        weak = await seed_pvp_eligible_player(players, tg_id=2, username="weak", length_cm=5)
        assert challenger.id is not None
        assert weak.id is not None
        await _seed_global_in_lobby(duels, lobby, challenger_id=challenger.id)

        with pytest.raises(PvpRequirementsNotMetError):
            await use_case.execute(MatchFromLobbyInput(accepter_tg_id=2))
