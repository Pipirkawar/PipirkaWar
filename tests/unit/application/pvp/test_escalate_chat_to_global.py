"""Unit-тесты `EscalateChatToGlobal` (Спринт 2.1.F.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import EscalateChatToGlobalInput
from pipirik_wars.application.pvp import (
    DuelEscalated,
    DuelEscalationSkipped,
    EscalateChatToGlobal,
)
from pipirik_wars.domain.pvp import Duel, DuelMode, DuelState
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
_EARLIER = _NOW - timedelta(minutes=3)


def _build() -> tuple[
    EscalateChatToGlobal,
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
    use_case = EscalateChatToGlobal(
        uow=uow,
        duels=duels,
        lobby=lobby,
        scheduler=scheduler,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, lobby, scheduler, audit, uow


async def _seed_chat_then_global(
    duels: FakeDuelRepository,
    *,
    challenger_id: int,
    challenged_id: int,
) -> Duel:
    pending = Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=DuelMode.CHAT_THEN_GLOBAL,
        hit_pct=10,
        expected_rounds=3,
        now=_EARLIER,
    )
    return await duels.add(pending)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_escalates_pending_chat_then_global(self) -> None:
        use_case, players, duels, lobby, scheduler, audit, uow = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_chat_then_global(
            duels,
            challenger_id=challenger.id,
            challenged_id=challenged.id,
        )
        assert pending.id is not None

        result = await use_case.execute(EscalateChatToGlobalInput(duel_id=pending.id))

        assert isinstance(result, DuelEscalated)
        assert result.duel.mode is DuelMode.GLOBAL_ONLY
        assert result.duel.challenged_id is None  # сбросилось на эскалации
        # запись в лобби есть
        assert any(r.duel_id == pending.id for r in lobby.rows)
        # job expiration запланирован
        assert pending.id in scheduler.scheduled_expirations
        assert scheduler.scheduled_expirations[pending.id].run_at == _NOW + timedelta(
            minutes=10,
        )
        assert len(audit.entries) == 1
        assert audit.entries[0].action is AuditAction.PVP_LOBBY_ESCALATED
        assert uow.commits == 1


class TestSkipScenarios:
    @pytest.mark.asyncio
    async def test_noop_when_duel_not_found(self) -> None:
        use_case, _p, _d, _l, scheduler, audit, _u = _build()
        result = await use_case.execute(EscalateChatToGlobalInput(duel_id=999))
        assert isinstance(result, DuelEscalationSkipped)
        assert result.reason == "not_found"
        assert scheduler.scheduled_expirations == {}
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_noop_when_already_accepted(self) -> None:
        use_case, players, duels, lobby, scheduler, audit, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_chat_then_global(
            duels,
            challenger_id=challenger.id,
            challenged_id=challenged.id,
        )
        assert pending.id is not None
        accepted = pending.accept(
            accepter_id=challenged.id,
            p1_length_cm=challenger.length.cm,
            p2_length_cm=challenged.length.cm,
            now=_NOW,
        )
        await duels.save(accepted)

        result = await use_case.execute(EscalateChatToGlobalInput(duel_id=pending.id))

        assert isinstance(result, DuelEscalationSkipped)
        assert result.reason == "not_pending_accept"
        assert lobby.rows == []
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_noop_when_already_cancelled(self) -> None:
        use_case, players, duels, lobby, scheduler, audit, _u = _build()
        challenger = await seed_pvp_eligible_player(players, tg_id=1)
        challenged = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert challenger.id is not None
        assert challenged.id is not None
        pending = await _seed_chat_then_global(
            duels,
            challenger_id=challenger.id,
            challenged_id=challenged.id,
        )
        assert pending.id is not None
        cancelled = pending.cancel(now=_NOW)
        await duels.save(cancelled)

        result = await use_case.execute(EscalateChatToGlobalInput(duel_id=pending.id))

        assert isinstance(result, DuelEscalationSkipped)
        assert result.reason == "not_pending_accept"
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_noop_for_chat_only_mode(self) -> None:
        use_case, players, duels, _l, _s, audit, _u = _build()
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
        result = await use_case.execute(EscalateChatToGlobalInput(duel_id=saved.id))
        assert isinstance(result, DuelEscalationSkipped)
        assert result.reason == "not_chat_then_global"
        assert audit.entries == []
        # state не меняется
        reloaded = await duels.get_by_id(duel_id=saved.id)
        assert reloaded is not None
        assert reloaded.state is DuelState.PENDING_ACCEPT
        assert reloaded.mode is DuelMode.CHAT_ONLY
