"""Unit-тесты `CloseBossLobby` (Спринт 3.3-B, ГДД §10.3).

Покрытие:
- happy-path: LOBBY → IN_BATTLE, save вызван, audit BOSS_FIGHT_STARTED
  записан с idempotency-key `boss_fight_started:{id}`;
- идемпотентность: повторный вызов на уже IN_BATTLE → was_already_closed=True,
  без аудита, без save;
- идемпотентность: на FINISHED → was_already_closed=True (NO-OP);
- идемпотентность: на CANCELLED → was_already_closed=True (NO-OP);
- ошибки: BossFightNotFoundError, без аудита, rollback.

ВАЖНО: scheduler-job на boss_round_tick / boss_fight_finish — это TODO 3.3-C.
В 3.3-B CloseBossLobby ограничен LOBBY → IN_BATTLE-переходом + audit-ом.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossLobbyClosed,
    CloseBossLobby,
)
from pipirik_wars.application.dto.inputs import CloseBossLobbyInput
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossFightStatus,
    BossKind,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=_LOBBY_MINUTES)
_SUMMONER_PLAYER_ID = 11
_BOSS_PLAYER_ID = 22


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    CloseBossLobby,
    FakeUnitOfWork,
    FakeBossFightRepository,
    FakeAuditLogger,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    use_case = CloseBossLobby(
        uow=uow,
        boss_fights=boss_fights,
        audit=audit,
        clock=used_clock,
    )
    return use_case, uow, boss_fights, audit, used_clock


async def _seed_boss_fight(
    *,
    boss_fights: FakeBossFightRepository,
    status: BossFightStatus = BossFightStatus.LOBBY,
) -> BossFight:
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=_SUMMONER_PLAYER_ID,
        boss_player_id=_BOSS_PLAYER_ID,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=42,
        initial_boss_length_cm=400,
    )
    fight = await boss_fights.add(fight)
    if status is BossFightStatus.IN_BATTLE:
        fight = await boss_fights.save(fight.mark_in_battle())
    elif status is BossFightStatus.FINISHED:
        fight = await boss_fights.save(fight.mark_in_battle())
        fight = await boss_fights.save(fight.mark_finished(finished_at=_LOBBY_ENDS_AT))
    elif status is BossFightStatus.CANCELLED:
        fight = await boss_fights.save(fight.mark_cancelled(cancelled_at=_LOBBY_ENDS_AT))
    return fight


def _input(*, boss_fight_id: int) -> CloseBossLobbyInput:
    return CloseBossLobbyInput(boss_fight_id=boss_fight_id)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_transitions_lobby_to_in_battle(self) -> None:
        use_case, uow, boss_fights, _audit, _clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights)
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert isinstance(result, BossLobbyClosed)
        assert result.was_already_closed is False
        assert result.boss_fight.id == fight.id
        assert result.boss_fight.status is BossFightStatus.IN_BATTLE
        # В репозитории — IN_BATTLE.
        assert boss_fights.rows[0].status is BossFightStatus.IN_BATTLE
        # Транзакция коммитится один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_boss_fight_started(self) -> None:
        use_case, _uow, boss_fights, audit, clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights)
        assert fight.id is not None

        await use_case.execute(_input(boss_fight_id=fight.id))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_FIGHT_STARTED
        assert entry.actor_id is None
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(fight.id)
        assert entry.before == {"status": BossFightStatus.LOBBY.value}
        assert entry.after == {"status": BossFightStatus.IN_BATTLE.value}
        assert entry.reason == "boss_fight_started"
        assert entry.idempotency_key == f"boss_fight_started:{fight.id}"
        assert entry.occurred_at == clock.now()


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_double_close_is_noop(self) -> None:
        """Второй CloseBossLobby подряд → was_already_closed=True, без аудита."""
        use_case, uow, boss_fights, audit, _clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights)
        assert fight.id is not None

        first = await use_case.execute(_input(boss_fight_id=fight.id))
        second = await use_case.execute(_input(boss_fight_id=fight.id))

        assert first.was_already_closed is False
        assert second.was_already_closed is True
        # Статус не меняется.
        assert second.boss_fight.status is BossFightStatus.IN_BATTLE
        # Аудит — только один (за первый close).
        assert len(audit.entries) == 1
        # Транзакции — две (одна для NO-OP коммита).
        assert uow.commits == 2
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_already_in_battle_is_noop(self) -> None:
        use_case, uow, boss_fights, audit, _clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights, status=BossFightStatus.IN_BATTLE)
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.was_already_closed is True
        assert result.boss_fight.status is BossFightStatus.IN_BATTLE
        assert audit.entries == []
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        use_case, _uow, boss_fights, audit, _clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights, status=BossFightStatus.FINISHED)
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.was_already_closed is True
        assert result.boss_fight.status is BossFightStatus.FINISHED
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        use_case, _uow, boss_fights, audit, _clock = _build_use_case()
        fight = await _seed_boss_fight(boss_fights=boss_fights, status=BossFightStatus.CANCELLED)
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.was_already_closed is True
        assert result.boss_fight.status is BossFightStatus.CANCELLED
        assert audit.entries == []


class TestErrors:
    @pytest.mark.asyncio
    async def test_boss_fight_not_found_raises(self) -> None:
        use_case, uow, _boss_fights, audit, _clock = _build_use_case()

        with pytest.raises(BossFightNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=9999))

        assert exc.value.boss_fight_id == 9999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0
