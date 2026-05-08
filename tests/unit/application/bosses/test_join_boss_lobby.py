"""Unit-тесты `JoinBossLobby` (Спринт 3.3-B, ГДД §10.1, §10.3).

Покрытие:
- happy-path: рейдер вступает в лобби; participant сохранён;
- audit `BOSS_RAIDER_JOINED` с idempotency-key;
- лок берётся (`LockReason.RAID`) с TTL = `lobby_ends_at - now`;
- ошибки: boss_fight не найден, лобби закрыто (IN_BATTLE/CANCELLED),
  player не найден, player заморожен, попытка боссу зайти рейдером,
  дублирующий вход (idempotency-protect), thickness < 4, длина < 20 см,
  активный лок (двойной join) → AlreadyInBossFightError.
- TTL clamp: вступление в момент конца лобби → лок берётся с минимумом 1 сек.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossLobbyJoined,
    JoinBossLobby,
)
from pipirik_wars.application.dto.inputs import JoinBossLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFight,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossKind,
    BossParticipant,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

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
    JoinBossLobby,
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
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = JoinBossLobby(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        locks=locks,
        balance=balance,
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


async def _seed_boss_fight(
    boss_fights: FakeBossFightRepository,
    *,
    summoner_player_id: int,
    boss_player_id: int,
    initial_boss_length_cm: int = 500,
    started_at: datetime = _NOW,
    lobby_ends_at: datetime = _LOBBY_ENDS_AT,
) -> BossFight:
    boss_fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        started_at=started_at,
        lobby_ends_at=lobby_ends_at,
        random_seed=12345,
        initial_boss_length_cm=initial_boss_length_cm,
    )
    return await boss_fights.add(boss_fight)


def _input(*, boss_fight_id: int, tg_id: int = _RAIDER_TG_ID) -> JoinBossLobbyInput:
    return JoinBossLobbyInput(boss_fight_id=boss_fight_id, tg_id=tg_id)


async def _seed_happy_path(
    *,
    players: FakePlayerRepository,
    boss_fights: FakeBossFightRepository,
    raider_thickness: int = 4,
    raider_length_cm: int = 100,
) -> tuple[BossFight, Player, Player, Player]:
    summoner = await _seed_player(
        players, tg_id=_SUMMONER_TG_ID, username="summoner", length_cm=200, thickness_level=9
    )
    boss = await _seed_player(
        players, tg_id=_BOSS_TG_ID, username="boss", length_cm=500, thickness_level=9
    )
    raider = await _seed_player(
        players,
        tg_id=_RAIDER_TG_ID,
        username="raider",
        length_cm=raider_length_cm,
        thickness_level=raider_thickness,
    )
    assert summoner.id is not None
    assert boss.id is not None
    boss_fight = await _seed_boss_fight(
        boss_fights,
        summoner_player_id=summoner.id,
        boss_player_id=boss.id,
        initial_boss_length_cm=boss.length.cm,
    )
    return boss_fight, summoner, boss, raider


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_creates_raider_participant(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            _audit,
            clock,
        ) = _build_use_case()
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert isinstance(result, BossLobbyJoined)
        assert result.boss_fight.id == boss_fight.id
        assert isinstance(result.participant, BossParticipant)
        assert result.participant.boss_fight_id == boss_fight.id
        assert result.participant.player_id == raider.id
        assert result.participant.is_summoner is False
        assert result.participant.length_at_join_cm == raider.length.cm
        assert result.participant.joined_at == clock.now()
        # Participant сохранён в репо.
        assert len(participants.rows) == 1
        # Транзакция коммитится один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_lock_taken_with_raid_reason(self) -> None:
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        lock = await lock_repo.get(actor_kind="player", actor_id=raider.id)
        assert lock is not None
        assert lock.reason is LockReason.RAID
        # TTL = lobby_ends_at - now.
        assert lock.expires_at == boss_fight.lobby_ends_at

    @pytest.mark.asyncio
    async def test_lock_ttl_clamped_to_minimum_when_lobby_just_about_to_close(self) -> None:
        """Если игрок зашёл в самые последние секунды лобби, лок берётся с минимумом."""
        clock = FakeClock(_LOBBY_ENDS_AT)  # ровно в момент конца лобби.
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            lock_repo,
            _audit,
            _clk,
        ) = _build_use_case(clock=clock)
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        lock = await lock_repo.get(actor_kind="player", actor_id=raider.id)
        assert lock is not None
        # TTL clamp = 1 секунда.
        assert lock.expires_at == _LOBBY_ENDS_AT + timedelta(seconds=1)


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_boss_raider_joined(self) -> None:
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_RAIDER_JOINED
        assert entry.actor_id == raider.tg_id
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(boss_fight.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["boss_fight_id"] == boss_fight.id
        assert entry.after["player_id"] == raider.id
        assert entry.after["length_at_join_cm"] == raider.length.cm
        assert entry.after["is_summoner"] is False
        assert entry.idempotency_key == f"boss_raider_joined:{boss_fight.id}:{raider.id}"
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
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_boss_fight_in_battle_raises_lobby_closed(self) -> None:
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
        boss_fight, _summoner, _boss, _raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        await boss_fights.save(boss_fight.mark_in_battle())

        with pytest.raises(BossFightLobbyClosedError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.boss_fight_id == boss_fight.id
        assert exc.value.status == "in_battle"
        assert participants.rows == []
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
        boss_fight, _summoner, _boss, _raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        await boss_fights.save(boss_fight.mark_cancelled(cancelled_at=_NOW))

        with pytest.raises(BossFightLobbyClosedError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.status == "cancelled"
        assert participants.rows == []
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
        # Сидим только саммонера и босса, но НЕ рейдера.
        summoner = await _seed_player(
            players, tg_id=_SUMMONER_TG_ID, username="summoner", length_cm=200, thickness_level=9
        )
        boss = await _seed_player(
            players, tg_id=_BOSS_TG_ID, username="boss", length_cm=500, thickness_level=9
        )
        assert summoner.id is not None
        assert boss.id is not None
        boss_fight = await _seed_boss_fight(
            boss_fights, summoner_player_id=summoner.id, boss_player_id=boss.id
        )
        assert boss_fight.id is not None

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.tg_id == _RAIDER_TG_ID
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_frozen_raises(self) -> None:
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
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        await players.save(raider.freeze(now=_NOW))

        with pytest.raises(PlayerFrozenError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.tg_id == _RAIDER_TG_ID
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_boss_player_cannot_join_as_raider(self) -> None:
        """ГДД §10.1: босс уже занят в рейде в роли босса — повторно нельзя."""
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
        boss_fight, _summoner, boss, _raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert boss.id is not None

        # Босс пытается зайти как рейдер своего же боя.
        with pytest.raises(AlreadyInBossFightError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id, tg_id=_BOSS_TG_ID))

        assert exc.value.player_id == boss.id
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_already_participant_raises_idempotency(self) -> None:
        """Повторный вход того же рейдера — раннее `AlreadyInBossFightError`."""
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
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        # Первый вход — happy.
        await use_case.execute(_input(boss_fight_id=boss_fight.id))
        assert len(participants.rows) == 1

        # Второй вход — `AlreadyInBossFightError`.
        with pytest.raises(AlreadyInBossFightError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.player_id == raider.id
        # Participants всё ещё один.
        assert len(participants.rows) == 1
        # Аудит — только за первый вход.
        assert len(audit.entries) == 1
        # Откатилась ровно одна транзакция (вторая).
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_required_raises(self) -> None:
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
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights, raider_thickness=3
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        with pytest.raises(BossFightRequirementError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 4
        assert exc.value.actual == 3
        assert exc.value.player_id == raider.id
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_length_below_required_raises(self) -> None:
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
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights, raider_length_cm=19
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        with pytest.raises(BossFightRequirementError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.requirement == "length_total"
        assert exc.value.required == 20
        assert exc.value.actual == 19
        assert exc.value.player_id == raider.id
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_active_lock_raises_already_in_boss_fight(self) -> None:
        """Игрок уже в каком-то локе (например, в дуэли) — JoinBossLobby режется."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        boss_fight, _summoner, _boss, raider = await _seed_happy_path(
            players=players, boss_fights=boss_fights
        )
        assert boss_fight.id is not None
        assert raider.id is not None

        # Имитируем: рейдер уже занят в активити-локе (например, PvP).
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=raider.id,
            reason=LockReason.PVP,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=10),
        )

        with pytest.raises(AlreadyInBossFightError) as exc:
            await use_case.execute(_input(boss_fight_id=boss_fight.id))

        assert exc.value.player_id == raider.id
        assert participants.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1
