"""Unit-тесты `EnqueueGlobalDuel` (Спринт 2.1.F.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import EnqueueGlobalDuelInput
from pipirik_wars.application.pvp import (
    EnqueueGlobalDuel,
    InvalidLobbyEnqueueError,
)
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
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
    EnqueueGlobalDuel,
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
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = EnqueueGlobalDuel(
        uow=uow,
        duels=duels,
        lobby=lobby,
        scheduler=scheduler,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, lobby, scheduler, audit, uow


async def _seed_pending_global(
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
    async def test_enqueues_global_only_duel(self) -> None:
        use_case, players, duels, lobby, scheduler, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_pending_global(duels, challenger_id=challenger.id)
        assert pending.id is not None

        result = await use_case.execute(EnqueueGlobalDuelInput(duel_id=pending.id))

        assert result.was_already_in_lobby is False
        assert result.duel.id == pending.id
        assert any(r.duel_id == pending.id for r in lobby.rows)
        assert pending.id in scheduler.scheduled_expirations
        assert scheduler.scheduled_expirations[pending.id].run_at == _NOW + timedelta(
            minutes=10,
        )
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        assert audit.entries[0].action is AuditAction.PVP_LOBBY_ENQUEUED

    @pytest.mark.asyncio
    async def test_idempotent_on_already_enqueued(self) -> None:
        use_case, players, duels, lobby, scheduler, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        assert challenger.id is not None
        pending = await _seed_pending_global(duels, challenger_id=challenger.id)
        assert pending.id is not None
        await lobby.enqueue(duel_id=pending.id, enqueued_at=_EARLIER)

        result = await use_case.execute(EnqueueGlobalDuelInput(duel_id=pending.id))

        assert result.was_already_in_lobby is True
        assert audit.entries == []  # повторный enqueue audit не пишет
        # но schedule expiration вызывается всегда (replace_existing)
        assert pending.id in scheduler.scheduled_expirations
        assert uow.commits == 1


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found(self) -> None:
        use_case, _p, _d, _l, _s, _a, uow = _build()
        with pytest.raises(DuelNotFoundError):
            await use_case.execute(EnqueueGlobalDuelInput(duel_id=999))
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_rejects_chat_only_mode(self) -> None:
        use_case, players, duels, _l, _s, _a, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = Duel.create_challenge(
            challenger_id=challenger.id,
            challenged_id=challenged.id,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_EARLIER,
        )
        saved = await duels.add(pending)
        assert saved.id is not None
        with pytest.raises(InvalidLobbyEnqueueError) as ei:
            await use_case.execute(EnqueueGlobalDuelInput(duel_id=saved.id))
        assert "mode=" in str(ei.value)

    @pytest.mark.asyncio
    async def test_rejects_already_accepted_duel(self) -> None:
        use_case, players, duels, _l, _s, _a, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_pending_global(duels, challenger_id=challenger.id)
        accepted = pending.accept(
            accepter_id=challenged.id,
            p1_length_cm=challenger.length.cm,
            p2_length_cm=challenged.length.cm,
            now=_NOW,
        )
        await duels.save(accepted)
        assert pending.id is not None
        with pytest.raises(InvalidLobbyEnqueueError) as ei:
            await use_case.execute(EnqueueGlobalDuelInput(duel_id=pending.id))
        assert "state=" in str(ei.value)
