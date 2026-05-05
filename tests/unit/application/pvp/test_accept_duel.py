"""Unit-тесты `AcceptDuel` (Спринт 2.1.D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import AcceptDuelInput
from pipirik_wars.application.pvp import AcceptDuel, DuelAccepted
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.progression.errors import AnticheatSoftBanError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    InvalidDuelStateError,
    NotADuelParticipantError,
    PvpRequirementsNotMetError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.security.errors import LockAlreadyHeldError
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeDuelRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=1)


def _build() -> tuple[
    AcceptDuel,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
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
    )
    return use_case, players, duels, audit, uow, lock_repo


async def _seed_pending_duel(
    duels: FakeDuelRepository,
    *,
    challenger_id: int,
    challenged_id: int | None,
    mode: DuelMode = DuelMode.CHAT_ONLY,
) -> Duel:
    pending = Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=mode,
        hit_pct=10,
        expected_rounds=3,
        now=_EARLIER,
    )
    return await duels.add(pending)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_accepts_targeted_challenge(self) -> None:
        use_case, players, duels, audit, uow, _lock_repo = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=challenged.id
        )
        assert pending.id is not None

        result = await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

        assert isinstance(result, DuelAccepted)
        duel = result.duel
        assert duel.state is DuelState.IN_PROGRESS
        assert duel.accepted_at == _NOW
        assert duel.p1_initial_length_cm == 50
        assert duel.p2_initial_length_cm == 40
        assert duel.pending_round is not None
        assert duel.pending_round.round_num == 1

        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PVP_DUEL_ACCEPTED
        assert entry.target_id == str(pending.id)
        assert entry.idempotency_key == f"pvp_duel_accepted:{pending.id}"

    @pytest.mark.asyncio
    async def test_accepts_global_only_sets_challenged_id(self) -> None:
        use_case, players, duels, _audit, _uow, _lock_repo = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await _seed_pending_duel(
            duels,
            challenger_id=challenger.id,
            challenged_id=None,
            mode=DuelMode.GLOBAL_ONLY,
        )
        assert pending.id is not None

        result = await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

        assert result.duel.challenged_id == accepter.id
        assert result.duel.state is DuelState.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_acquires_lock_on_accepter(self) -> None:
        use_case, players, duels, _a, _u, lock_repo = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=accepter.id
        )
        assert pending.id is not None

        await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

        assert lock_repo.locks[("player", accepter.id)].reason is LockReason.PVP


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found(self) -> None:
        use_case, players, _d, _a, uow, _l = _build()
        await seed_pvp_eligible_player(players, tg_id=2)
        with pytest.raises(DuelNotFoundError):
            await use_case.execute(AcceptDuelInput(duel_id=999, tg_id=2))
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_pending_duel(duels, challenger_id=challenger.id, challenged_id=999)
        assert pending.id is not None
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=999))

    @pytest.mark.asyncio
    async def test_challenger_disappeared(self) -> None:
        # Защитный кейс: челленджер удалён из БД (FK violation).
        use_case, players, duels, _a, _u, _l = _build()
        accepter = await seed_pvp_eligible_player(players, tg_id=2)
        assert accepter.id is not None
        pending = await _seed_pending_duel(duels, challenger_id=999, challenged_id=accepter.id)
        assert pending.id is not None
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

    @pytest.mark.asyncio
    async def test_accepter_below_pvp_requirements(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        # длина 5 — ниже min_length_cm=20
        weak = await seed_pvp_eligible_player(players, tg_id=2, length_cm=5, username="bob")
        assert challenger.id is not None
        assert weak.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=weak.id
        )
        assert pending.id is not None
        with pytest.raises(PvpRequirementsNotMetError) as exc:
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))
        assert exc.value.requirement == "length"

    @pytest.mark.asyncio
    async def test_accepter_anticheat_banned(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        ban_until = _NOW + timedelta(days=2)
        await players.save(accepter.with_anticheat_ban(until=ban_until, now=_NOW))
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=accepter.id
        )
        assert pending.id is not None
        with pytest.raises(AnticheatSoftBanError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

    @pytest.mark.asyncio
    async def test_accepter_already_locked(self) -> None:
        use_case, players, duels, _a, _u, lock_repo = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=accepter.id,
            reason=LockReason.FOREST,
            now=_NOW,
            expires_at=_NOW + timedelta(hours=1),
        )
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=accepter.id
        )
        assert pending.id is not None
        with pytest.raises(LockAlreadyHeldError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))

    @pytest.mark.asyncio
    async def test_cannot_accept_own_challenge(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        # GLOBAL_ONLY pending — челленджер пытается принять сам.
        pending = await _seed_pending_duel(
            duels,
            challenger_id=challenger.id,
            challenged_id=None,
            mode=DuelMode.GLOBAL_ONLY,
        )
        assert pending.id is not None
        with pytest.raises(NotADuelParticipantError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=1))

    @pytest.mark.asyncio
    async def test_third_party_cannot_accept_targeted(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        target = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        third = await seed_pvp_eligible_player(players, tg_id=3, username="carol")
        assert challenger.id is not None
        assert target.id is not None
        assert third.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=target.id
        )
        assert pending.id is not None
        with pytest.raises(NotADuelParticipantError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=3))

    @pytest.mark.asyncio
    async def test_cannot_accept_completed_duel(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        accepter = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert accepter.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=accepter.id
        )
        assert pending.id is not None
        # вручную сдвинуть в CANCELLED
        cancelled = pending.cancel(now=_NOW)
        await duels.save(cancelled)
        with pytest.raises(InvalidDuelStateError):
            await use_case.execute(AcceptDuelInput(duel_id=pending.id, tg_id=2))
