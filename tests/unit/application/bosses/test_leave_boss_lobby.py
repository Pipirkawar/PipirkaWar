"""Unit-тесты `LeaveBossLobby` (Спринт 3.3-B, ГДД §10.3).

Покрытие:
- happy-path: рейдер выходит, participant удалён, лок снят;
- audit `BOSS_RAIDER_LEFT` с idempotency-key;
- саммонер тоже может выйти (без cancel-боя — это TODO 3.3-C);
- ошибки: boss_fight не найден, лобби закрыто (IN_BATTLE/CANCELLED),
  player не найден, игрок не участник боя (NotInBossFightError);
- идемпотентность: повторный leave того же игрока → NotInBossFightError.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossLobbyLeft,
    LeaveBossLobby,
)
from pipirik_wars.application.dto.inputs import LeaveBossLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossKind,
    BossParticipant,
    NotInBossFightError,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=_LOBBY_MINUTES)
_SUMMONER_TG_ID = 10
_BOSS_TG_ID = 20
_RAIDER_TG_ID = 100


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    LeaveBossLobby,
    FakeUnitOfWork,
    FakePlayerRepository,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    use_case = LeaveBossLobby(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        locks=locks,
        audit=audit,
        clock=used_clock,
    )
    return (
        use_case,
        uow,
        players,
        boss_fights,
        boss_participants,
        lock_repo,
        audit,
        used_clock,
    )


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str,
    length_cm: int = 100,
    thickness_level: int = 4,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


async def _seed_boss_fight_with_summoner_and_raider(
    *,
    players: FakePlayerRepository,
    boss_fights: FakeBossFightRepository,
    boss_participants: FakeBossParticipantRepository,
) -> tuple[BossFight, Player, Player, Player, BossParticipant, BossParticipant]:
    summoner = await _seed_player(
        players, tg_id=_SUMMONER_TG_ID, username="summoner", length_cm=200, thickness_level=9
    )
    boss = await _seed_player(
        players, tg_id=_BOSS_TG_ID, username="boss", length_cm=500, thickness_level=9
    )
    raider = await _seed_player(players, tg_id=_RAIDER_TG_ID, username="raider", length_cm=100)
    assert summoner.id is not None
    assert boss.id is not None
    assert raider.id is not None
    boss_fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner.id,
        boss_player_id=boss.id,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=12345,
        initial_boss_length_cm=boss.length.cm,
    )
    boss_fight = await boss_fights.add(boss_fight)
    assert boss_fight.id is not None

    summoner_p = await boss_participants.add(
        BossParticipant.raider(
            boss_fight_id=boss_fight.id,
            player_id=summoner.id,
            is_summoner=True,
            length_at_join_cm=summoner.length.cm,
            joined_at=_NOW,
        )
    )
    raider_p = await boss_participants.add(
        BossParticipant.raider(
            boss_fight_id=boss_fight.id,
            player_id=raider.id,
            is_summoner=False,
            length_at_join_cm=raider.length.cm,
            joined_at=_NOW + timedelta(minutes=1),
        )
    )
    return boss_fight, summoner, boss, raider, summoner_p, raider_p


def _input(*, boss_fight_id: int, tg_id: int = _RAIDER_TG_ID) -> LeaveBossLobbyInput:
    return LeaveBossLobbyInput(boss_fight_id=boss_fight_id, tg_id=tg_id)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_removes_raider_participant(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            raider,
            _summoner_p,
            raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert isinstance(result, BossLobbyLeft)
        assert result.boss_fight.id == boss_fight.id
        assert result.removed_participant.player_id == raider.id
        assert result.removed_participant.is_summoner is False
        assert result.removed_participant.length_at_join_cm == raider_p.length_at_join_cm
        # Рейдер удалён из participants, саммонер остался.
        assert len(participants.rows) == 1
        assert participants.rows[0].player_id != raider.id
        # Транзакция коммитится один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_lock_released(self) -> None:
        (
            use_case,
            _uow,
            players,
            boss_fights,
            participants,
            lock_repo,
            _audit,
            clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        # Имитируем активный лок рейдера (заведён JoinBossLobby).
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=raider.id,
            reason=LockReason.RAID,
            now=clock.now(),
            expires_at=boss_fight.lobby_ends_at,
        )
        assert await lock_repo.get(actor_kind="player", actor_id=raider.id) is not None

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        # Лок снят.
        assert await lock_repo.get(actor_kind="player", actor_id=raider.id) is None

    @pytest.mark.asyncio
    async def test_lock_release_is_noop_when_no_lock(self) -> None:
        """release — NO-OP, если лока нет (упавший процесс / повторный leave)."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        # Лок специально не берём.
        assert lock_repo.locks == {}

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_summoner_can_leave_without_cancelling_fight(self) -> None:
        """Саммонер выходит — бой остаётся в LOBBY (TODO 3.3-C)."""
        (
            use_case,
            _uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        assert summoner.id is not None

        result = await use_case.execute(_input(boss_fight_id=boss_fight.id, tg_id=_SUMMONER_TG_ID))

        assert result.removed_participant.is_summoner is True
        assert result.removed_participant.player_id == summoner.id
        # Бой по-прежнему LOBBY (CancelBossFight — отдельный use-case в 3.3-C).
        assert boss_fights.rows[0].is_in_lobby
        # Остался только рейдер.
        assert len(participants.rows) == 1
        assert participants.rows[0].is_summoner is False


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_boss_raider_left(self) -> None:
        (
            use_case,
            _uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            raider,
            _summoner_p,
            raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_RAIDER_LEFT
        assert entry.actor_id == raider.tg_id
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(boss_fight.id)
        assert entry.before is not None
        assert entry.before["boss_fight_id"] == boss_fight.id
        assert entry.before["player_id"] == raider.id
        assert entry.before["is_summoner"] is False
        assert entry.before["length_at_join_cm"] == raider_p.length_at_join_cm
        assert entry.after is None
        assert entry.idempotency_key == (
            f"boss_raider_left:{boss_fight.id}:{raider.id}:{raider_p.joined_at.isoformat()}"
        )
        assert entry.occurred_at == clock.now()


class TestErrors:
    @pytest.mark.asyncio
    async def test_boss_fight_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            _players,
            _boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()

        with pytest.raises(BossFightNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=999))

        assert exc.value.boss_fight_id == 999
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_boss_fight_in_battle_raises_lobby_closed(self) -> None:
        """LOBBY → IN_BATTLE: leave уже невозможен."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        await boss_fights.save(boss_fight.mark_in_battle())

        with pytest.raises(BossFightLobbyClosedError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.status == "in_battle"
        # Participants не тронуты.
        assert len(participants.rows) == 2
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_boss_fight_cancelled_raises_lobby_closed(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        await boss_fights.save(boss_fight.mark_cancelled(cancelled_at=_NOW))

        with pytest.raises(BossFightLobbyClosedError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.status == "cancelled"
        assert len(participants.rows) == 2
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None

        # tg_id, который мы не сидили вообще.
        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id, tg_id=99999))

        assert exc.value.tg_id == 99999
        assert len(participants.rows) == 2
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_in_boss_fight_raises(self) -> None:
        """Игрок есть в репо, но НЕ участник этого боя."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            _raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        # Сидим лишнего игрока, который не участник этого боя.
        outsider = await _seed_player(players, tg_id=200, username="outsider", length_cm=100)
        assert outsider.id is not None

        with pytest.raises(NotInBossFightError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id, tg_id=200))

        assert exc.value.boss_fight_id == boss_fight.id
        assert exc.value.player_id == outsider.id
        assert len(participants.rows) == 2
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_double_leave_raises_not_in_boss_fight(self) -> None:
        """Повторный leave того же игрока — `NotInBossFightError` (idempotency)."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        (
            boss_fight,
            _summoner,
            _boss,
            raider,
            _summoner_p,
            _raider_p,
        ) = await _seed_boss_fight_with_summoner_and_raider(
            players=players,
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        # Первый leave — happy.
        await use_case.execute(_input(boss_fight_id=boss_fight.id))
        # Второй leave того же игрока — рейдера уже нет в participants.
        with pytest.raises(NotInBossFightError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.player_id == raider.id
        # Аудит — только за первый leave.
        assert len(audit.entries) == 1
        assert uow.rollbacks == 1
