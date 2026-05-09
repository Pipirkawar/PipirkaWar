"""Unit-тесты `CancelBossFight` (Спринт 3.3-D, ГДД §10.3).

Покрытие:
- happy-path: саммонер отменяет рейд из LOBBY → CANCELLED;
  audit `BOSS_FIGHT_CANCELLED` записан с idempotency-key
  `boss_fight_cancelled:{id}`, locks снимаются у саммонера / рейдеров /
  босса, lobby-close-job (+ best-effort round-tick / fight-finish)
  отозваны;
- идемпотентность: повторный вызов на CANCELLED → no-op,
  `was_already_cancelled=True`, audit/locks/scheduler не трогаются;
- error-cases: boss-fight не найден, player не найден, не саммонер,
  не в LOBBY (IN_BATTLE / FINISHED).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossFightCancelled,
    CancelBossFight,
)
from pipirik_wars.application.dto.inputs import CancelBossFightInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossFightStatus,
    BossKind,
    BossParticipant,
    InvalidBossFightStateError,
    NotAuthorizedToCancelBossError,
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
    FakeDelayedJobScheduler,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=20)
_SUMMONER_TG_ID = 1001
_SUMMONER_PLAYER_ID = 100
_RAIDER_TG_ID = 2001
_RAIDER_PLAYER_ID = 200
_BOSS_PLAYER_ID = 300
_RANDOM_SEED = 42
_INITIAL_BOSS_LENGTH = 400


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    CancelBossFight,
    FakeUnitOfWork,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakePlayerRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeDelayedJobScheduler,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    players = FakePlayerRepository()
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    scheduler = FakeDelayedJobScheduler()
    used_clock = clock or FakeClock(_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    use_case = CancelBossFight(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        locks=locks,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return (
        use_case,
        uow,
        boss_fights,
        boss_participants,
        players,
        lock_repo,
        audit,
        scheduler,
        used_clock,
    )


async def _seed_boss_fight(
    boss_fights: FakeBossFightRepository,
    *,
    summoner_player_id: int = _SUMMONER_PLAYER_ID,
    boss_player_id: int = _BOSS_PLAYER_ID,
    status: BossFightStatus = BossFightStatus.LOBBY,
) -> BossFight:
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=_RANDOM_SEED,
        initial_boss_length_cm=_INITIAL_BOSS_LENGTH,
    )
    saved = await boss_fights.add(fight)
    if status is BossFightStatus.LOBBY:
        return saved
    if status is BossFightStatus.IN_BATTLE:
        return await boss_fights.save(saved.mark_in_battle())
    if status is BossFightStatus.FINISHED:
        return await boss_fights.save(
            saved.mark_in_battle().mark_finished(finished_at=_LOBBY_ENDS_AT)
        )
    if status is BossFightStatus.CANCELLED:
        return await boss_fights.save(saved.mark_cancelled(cancelled_at=_NOW))
    raise ValueError(f"unsupported status {status!r}")


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str = "user",
    length_cm: int = 100,
    thickness_level: int = 7,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


async def _seed_summoner_participant(
    participants: FakeBossParticipantRepository,
    *,
    boss_fight_id: int,
    player_id: int,
    length_at_join_cm: int = 100,
) -> BossParticipant:
    summoner = BossParticipant(
        boss_fight_id=boss_fight_id,
        player_id=player_id,
        is_summoner=True,
        length_at_join_cm=length_at_join_cm,
        joined_at=_NOW,
    )
    return await participants.add(summoner)


async def _seed_raider_participant(
    participants: FakeBossParticipantRepository,
    *,
    boss_fight_id: int,
    player_id: int,
    length_at_join_cm: int = 80,
    minutes_after: int = 1,
) -> BossParticipant:
    raider = BossParticipant(
        boss_fight_id=boss_fight_id,
        player_id=player_id,
        is_summoner=False,
        length_at_join_cm=length_at_join_cm,
        joined_at=_NOW + timedelta(minutes=minutes_after),
    )
    return await participants.add(raider)


async def _acquire_player_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    now: datetime,
) -> None:
    await lock_repo.try_acquire(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.RAID,
        now=now,
        expires_at=now + timedelta(minutes=80),
    )


def _input(*, boss_fight_id: int, tg_id: int) -> CancelBossFightInput:
    return CancelBossFightInput(boss_fight_id=boss_fight_id, tg_id=tg_id)


# ---------- Happy path ----------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_summoner_cancels_from_lobby(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            participants,
            players,
            lock_repo,
            _audit,
            scheduler,
            clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(boss_fights, summoner_player_id=summoner.id)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )
        await _acquire_player_lock(lock_repo, player_id=summoner.id, now=clock.now())

        result = await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert isinstance(result, BossFightCancelled)
        assert result.was_already_cancelled is False
        assert result.boss_fight.id == fight.id
        assert result.boss_fight.status is BossFightStatus.CANCELLED
        # Рейд-бой сохранён в репо в статусе CANCELLED.
        stored = await boss_fights.get_by_id(boss_fight_id=fight.id)
        assert stored is not None
        assert stored.status is BossFightStatus.CANCELLED
        assert stored.finished_at == clock.now()
        # Лок саммонера снят.
        assert await lock_repo.get(actor_kind="player", actor_id=summoner.id) is None
        # lobby-close-job отозван (+ round-tick + fight-finish best-effort).
        assert fight.id in scheduler.cancelled_boss_lobby_close
        assert fight.id in scheduler.cancelled_boss_round_tick
        assert fight.id in scheduler.cancelled_boss_fight_finish
        # Транзакция коммитится.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_locks_released_for_summoner_raiders_and_boss(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            players,
            lock_repo,
            _audit,
            _scheduler,
            clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        raider = await _seed_player(players, tg_id=_RAIDER_TG_ID, username="raider")
        assert raider.id is not None
        boss = await _seed_player(players, tg_id=9999, username="bossplr")
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
        )
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )
        await _seed_raider_participant(participants, boss_fight_id=fight.id, player_id=raider.id)
        await _acquire_player_lock(lock_repo, player_id=summoner.id, now=clock.now())
        await _acquire_player_lock(lock_repo, player_id=raider.id, now=clock.now())
        await _acquire_player_lock(lock_repo, player_id=boss.id, now=clock.now())

        await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert await lock_repo.get(actor_kind="player", actor_id=summoner.id) is None
        assert await lock_repo.get(actor_kind="player", actor_id=raider.id) is None
        assert await lock_repo.get(actor_kind="player", actor_id=boss.id) is None

    @pytest.mark.asyncio
    async def test_lock_release_is_noop_when_no_lock(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            players,
            lock_repo,
            _audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(boss_fights, summoner_player_id=summoner.id)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )
        # Лок не брался (например, истёк).
        assert await lock_repo.get(actor_kind="player", actor_id=summoner.id) is None

        result = await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert result.was_already_cancelled is False
        assert result.boss_fight.status is BossFightStatus.CANCELLED


# ---------- Audit ----------


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_boss_fight_cancelled(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        raider = await _seed_player(players, tg_id=_RAIDER_TG_ID, username="raider")
        assert raider.id is not None
        fight = await _seed_boss_fight(boss_fights, summoner_player_id=summoner.id)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )
        await _seed_raider_participant(participants, boss_fight_id=fight.id, player_id=raider.id)

        await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_FIGHT_CANCELLED
        assert entry.actor_id == _SUMMONER_TG_ID
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(fight.id)
        assert entry.before is not None
        assert entry.before["status"] == BossFightStatus.LOBBY.value
        assert entry.after is not None
        assert entry.after["status"] == BossFightStatus.CANCELLED.value
        assert entry.after["participants_count"] == 2
        assert entry.after["cancelled_at"] == clock.now().isoformat()
        assert entry.reason == "boss_fight_cancelled_by_summoner"
        assert entry.idempotency_key == f"boss_fight_cancelled:{fight.id}"
        assert entry.occurred_at == clock.now()


# ---------- Idempotency ----------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            _participants,
            players,
            _lock_repo,
            audit,
            scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(
            boss_fights,
            summoner_player_id=summoner.id,
            status=BossFightStatus.CANCELLED,
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert result.was_already_cancelled is True
        assert result.boss_fight.status is BossFightStatus.CANCELLED
        # Audit НЕ пишется при no-op.
        assert audit.entries == []
        # scheduler.cancel НЕ вызывается при no-op.
        assert scheduler.cancelled_boss_lobby_close == []
        assert scheduler.cancelled_boss_round_tick == []
        assert scheduler.cancelled_boss_fight_finish == []
        # Транзакция всё равно коммитится (выходит из `async with self._uow`).
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_double_cancel_idempotent(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(boss_fights, summoner_player_id=summoner.id)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )

        first = await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))
        second = await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert first.was_already_cancelled is False
        assert second.was_already_cancelled is True
        # Audit-запись только одна (от первого вызова).
        assert len(audit.entries) == 1


# ---------- Errors ----------


class TestErrors:
    @pytest.mark.asyncio
    async def test_boss_fight_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            _boss_fights,
            _participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")

        with pytest.raises(BossFightNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=9999, tg_id=_SUMMONER_TG_ID))

        assert exc.value.boss_fight_id == 9999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            participants,
            _players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(boss_fights)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=_SUMMONER_PLAYER_ID
        )

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=fight.id, tg_id=999))

        assert exc.value.tg_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_non_summoner_cannot_cancel(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            participants,
            players,
            _lock_repo,
            audit,
            scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        raider = await _seed_player(players, tg_id=_RAIDER_TG_ID, username="raider")
        assert raider.id is not None
        fight = await _seed_boss_fight(boss_fights, summoner_player_id=summoner.id)
        assert fight.id is not None
        await _seed_summoner_participant(
            participants, boss_fight_id=fight.id, player_id=summoner.id
        )
        await _seed_raider_participant(participants, boss_fight_id=fight.id, player_id=raider.id)

        with pytest.raises(NotAuthorizedToCancelBossError) as exc:
            await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_RAIDER_TG_ID))

        assert exc.value.boss_fight_id == fight.id
        assert exc.value.player_id == raider.id
        assert exc.value.summoner_player_id == summoner.id
        assert audit.entries == []
        assert uow.rollbacks == 1
        # scheduler не дёргался — рейд остался в LOBBY.
        assert scheduler.cancelled_boss_lobby_close == []
        stored = await boss_fights.get_by_id(boss_fight_id=fight.id)
        assert stored is not None
        assert stored.status is BossFightStatus.LOBBY

    @pytest.mark.asyncio
    async def test_in_battle_raises_invalid_state(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            _participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(
            boss_fights,
            summoner_player_id=summoner.id,
            status=BossFightStatus.IN_BATTLE,
        )
        assert fight.id is not None

        with pytest.raises(InvalidBossFightStateError) as exc:
            await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert exc.value.boss_fight_id == fight.id
        assert exc.value.expected == BossFightStatus.LOBBY.value
        assert exc.value.actual == BossFightStatus.IN_BATTLE.value
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_finished_raises_invalid_state(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            _participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        summoner = await _seed_player(players, tg_id=_SUMMONER_TG_ID, username="summoner")
        assert summoner.id is not None
        fight = await _seed_boss_fight(
            boss_fights,
            summoner_player_id=summoner.id,
            status=BossFightStatus.FINISHED,
        )
        assert fight.id is not None

        with pytest.raises(InvalidBossFightStateError) as exc:
            await use_case.execute(_input(boss_fight_id=fight.id, tg_id=_SUMMONER_TG_ID))

        assert exc.value.boss_fight_id == fight.id
        assert exc.value.expected == BossFightStatus.LOBBY.value
        assert exc.value.actual == BossFightStatus.FINISHED.value
        assert audit.entries == []
        assert uow.rollbacks == 1
