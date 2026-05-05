"""Unit-тесты `CancelDuel` (Спринт 2.1.D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import CancelDuelInput
from pipirik_wars.application.pvp import CancelDuel, DuelCancelled
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    InvalidDuelStateError,
    NotADuelParticipantError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
    FakeDuelRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=2)


def _build() -> tuple[
    CancelDuel,
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
    use_case = CancelDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, audit, uow, lock_repo


async def _seed_pending_duel(
    duels: FakeDuelRepository,
    *,
    challenger_id: int,
    challenged_id: int | None = None,
    mode: DuelMode = DuelMode.CHAT_THEN_GLOBAL,
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
    async def test_cancels_own_pending_challenge(self) -> None:
        use_case, players, duels, audit, uow, lock_repo = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        # ставим лок, как `ChallengeDuel` сделал бы
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=challenger.id,
            reason=LockReason.PVP,
            now=_EARLIER,
            expires_at=_NOW + timedelta(minutes=30),
        )
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=challenged.id
        )
        assert pending.id is not None

        result = await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=1))

        assert isinstance(result, DuelCancelled)
        assert result.was_already_cancelled is False
        assert result.duel.state is DuelState.CANCELLED
        assert result.duel.cancelled_at == _NOW

        # лок снят
        assert ("player", challenger.id) not in lock_repo.locks
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PVP_DUEL_CANCELLED
        assert entry.target_id == str(pending.id)
        assert entry.idempotency_key == f"pvp_duel_cancelled:{pending.id}"

    @pytest.mark.asyncio
    async def test_idempotent_on_already_cancelled(self) -> None:
        use_case, players, duels, audit, uow, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_pending_duel(
            duels,
            challenger_id=challenger.id,
            mode=DuelMode.GLOBAL_ONLY,
        )
        assert pending.id is not None
        cancelled = pending.cancel(now=_EARLIER)
        await duels.save(cancelled)

        result = await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=1))

        assert result.was_already_cancelled is True
        # ни audit, ни новые мутации
        assert audit.entries == []
        assert uow.commits == 1
        assert uow.rollbacks == 0


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found(self) -> None:
        use_case, players, _d, _a, uow, _l = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        with pytest.raises(DuelNotFoundError):
            await use_case.execute(CancelDuelInput(duel_id=999, tg_id=1))
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, mode=DuelMode.GLOBAL_ONLY
        )
        assert pending.id is not None
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=999))

    @pytest.mark.asyncio
    async def test_only_challenger_can_cancel(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=challenged.id
        )
        assert pending.id is not None
        with pytest.raises(NotADuelParticipantError):
            await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=2))

    @pytest.mark.asyncio
    async def test_cannot_cancel_in_progress_duel(self) -> None:
        use_case, players, duels, _a, _u, _l = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_pending_duel(
            duels, challenger_id=challenger.id, challenged_id=challenged.id
        )
        accepted = pending.accept(
            accepter_id=challenged.id,
            p1_length_cm=challenger.length.cm,
            p2_length_cm=challenged.length.cm,
            now=_NOW,
        )
        await duels.save(accepted)
        assert pending.id is not None
        with pytest.raises(InvalidDuelStateError):
            await use_case.execute(CancelDuelInput(duel_id=pending.id, tg_id=1))
