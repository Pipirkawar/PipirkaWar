"""Unit-тесты `FinishBossFight` (Спринт 3.3-C, ГДД §10.5–§10.6).

Покрытие:

* happy-path **победа рейдеров** (`current_boss_length_cm < victory_threshold_cm`):
  каждый живой рейдер получает `+initial_boss_length_cm // N` см через
  `ILengthGranter.grant(source=RAID_REWARD)`; per-player ролл скроллов
  пишется audit-эвентами `SCROLL_DROP`; босс получает `LENGTH_REVOKE`
  через прямой `Player.with_length(...)` с floor-clamp до
  `victory_threshold_cm`; `boss_fight.status=FINISHED`; activity-locks
  всех живых рейдеров и босса сняты; audit
  `BOSS_FIGHT_FINISHED + BOSS_REWARDS_GRANTED` + per-scroll `SCROLL_DROP`;
* happy-path **поражение рейдеров** (`current_boss_length_cm >= victory_threshold_cm`):
  босс получает `+sum(length_at_join_cm)` через `ILengthGranter`;
  рейдер-вычеты отсутствуют (вынесено в 3.3-D, см. docstring модуля);
  `LENGTH_REVOKE` НЕ пишется; `SCROLL_DROP` НЕ пишется;
* идемпотентность: повторный вызов на `FINISHED`/`CANCELLED` —
  no-op (`was_already_finished=True`), audit/grant НЕ пишутся;
* инвариант `LOBBY` → `InvalidBossFightStateError`;
* ошибки: `BossFightNotFoundError`, `PlayerNotFoundError` (при revoke
  длины пропавшего босс-игрока).

Зависимости: `AddLength` (реальный `ILengthGranter`) +
`FakeAnticheatRepository` — прибавки идут через настоящий cap-trip-wire,
вычет с босса — прямой `Player.with_length` через архитектурный гард в
`tests/unit/architecture/test_length_grant_guard.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossFightFinished,
    BossScrollDrop,
    FinishBossFight,
)
from pipirik_wars.application.dto.inputs import FinishBossFightInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossFightStatus,
    BossKind,
    BossParticipant,
    InvalidBossFightStateError,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Username,
)
from pipirik_wars.domain.security import ActivityLock, LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_LOBBY_ENDS_AT = _NOW - timedelta(minutes=_LOBBY_MINUTES)
_BATTLE_NOW = _NOW
_STARTED = _NOW - timedelta(hours=2)

_SUMMONER_TG = 11
_BOSS_TG = 22
_RAIDER_2_TG = 33
_RAIDER_3_TG = 44

_INITIAL_BOSS_LENGTH_CM = 400
_RANDOM_SEED = 42

_BOSSES_CONFIG = build_valid_balance().bosses
_VICTORY_THRESHOLD_CM = _BOSSES_CONFIG.victory_threshold_cm


@dataclass(frozen=True)
class _Setup:
    use_case: FinishBossFight
    players: FakePlayerRepository
    boss_fights: FakeBossFightRepository
    boss_participants: FakeBossParticipantRepository
    audit: FakeAuditLogger
    uow: FakeUnitOfWork
    clock: FakeClock
    lock_repo: FakeActivityLockRepository
    scheduler: FakeDelayedJobScheduler


def _build_setup(*, seed: int = 1, clock: FakeClock | None = None) -> _Setup:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    scheduler = FakeDelayedJobScheduler()
    balance_full = FakeBalanceConfig(build_valid_balance())
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance_full,
        clock=used_clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = FinishBossFight(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        length_granter=length_granter,
        locks=locks,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
        balance=_BOSSES_CONFIG,
        random_factory=lambda s: FakeRandom(seed=seed),
    )
    return _Setup(
        use_case=use_case,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        audit=audit,
        uow=uow,
        clock=used_clock,
        lock_repo=lock_repo,
        scheduler=scheduler,
    )


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str,
    length_cm: int = 50,
) -> Player:
    player = await players.add(
        Player.new(tg_id=tg_id, username=Username(value=username), now=_STARTED),
    )
    if length_cm != player.length.cm:
        player = await players.save(
            player.with_length(Length(cm=length_cm), now=_STARTED),
        )
    assert player.id is not None
    return player


async def _seed_boss_fight(
    *,
    boss_fights: FakeBossFightRepository,
    boss_participants: FakeBossParticipantRepository,
    summoner_player_id: int,
    boss_player_id: int,
    status: BossFightStatus = BossFightStatus.IN_BATTLE,
    raider_player_ids: tuple[int, ...] | None = None,
    initial_boss_length_cm: int = _INITIAL_BOSS_LENGTH_CM,
    current_boss_length_cm: int | None = None,
    current_round: int = 0,
    raider_length_at_join_cm: int = 100,
) -> BossFight:
    """Создать рейд-бой в нужном статусе + посадить рейдеров.

    `raider_player_ids` — список реальных `player_id`-ов в порядке вступления;
    первый — саммонер (`is_summoner=True`). По умолчанию — `(summoner_player_id,)`.
    """
    if raider_player_ids is None:
        raider_player_ids = (summoner_player_id,)
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        started_at=_NOW - timedelta(minutes=_LOBBY_MINUTES + 5),
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=_RANDOM_SEED,
        initial_boss_length_cm=initial_boss_length_cm,
    )
    fight = await boss_fights.add(fight)

    if status is BossFightStatus.LOBBY:
        pass
    elif status is BossFightStatus.IN_BATTLE:
        fight = await boss_fights.save(fight.mark_in_battle())
    elif status is BossFightStatus.FINISHED:
        fight = await boss_fights.save(fight.mark_in_battle())
        fight = await boss_fights.save(fight.mark_finished(finished_at=_BATTLE_NOW))
    elif status is BossFightStatus.CANCELLED:
        fight = await boss_fights.save(fight.mark_cancelled(cancelled_at=_BATTLE_NOW))

    if current_boss_length_cm is not None or current_round > 0:
        if current_boss_length_cm is not None:
            fight = fight.with_boss_length(length_cm=current_boss_length_cm)
        for _ in range(current_round):
            fight = fight.with_round_advanced()
        fight = await boss_fights.save(fight)

    assert fight.id is not None
    for i, player_id in enumerate(raider_player_ids):
        await boss_participants.add(
            BossParticipant.raider(
                boss_fight_id=fight.id,
                player_id=player_id,
                is_summoner=(i == 0),
                length_at_join_cm=raider_length_at_join_cm,
                joined_at=_NOW + timedelta(seconds=i),
            )
        )

    return fight


async def _seed_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    expires_at: datetime,
) -> None:
    lock_repo.locks[("player", player_id)] = ActivityLock(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.RAID,
        acquired_at=_STARTED,
        expires_at=expires_at,
    )


# ---------- Happy path: raiders win ----------


class TestRaidersVictory:
    """current_boss_length_cm < victory_threshold_cm → рейдеры победили."""

    @pytest.mark.asyncio
    async def test_raiders_win_grants_rewards_and_revokes_boss_length(self) -> None:
        s = _build_setup(seed=1)

        summoner = await _seed_player(
            s.players, tg_id=_SUMMONER_TG, username="summoner", length_cm=50
        )
        raider2 = await _seed_player(
            s.players, tg_id=_RAIDER_2_TG, username="raider2", length_cm=50
        )
        raider3 = await _seed_player(
            s.players, tg_id=_RAIDER_3_TG, username="raider3", length_cm=50
        )
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert (
            summoner.id is not None
            and raider2.id is not None
            and raider3.id is not None
            and boss.id is not None
        )

        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id, raider2.id, raider3.id),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        for pid in (summoner.id, raider2.id, raider3.id, boss.id):
            await _seed_lock(s.lock_repo, player_id=pid, expires_at=_NOW + timedelta(hours=1))

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert isinstance(result, BossFightFinished)
        assert result.was_already_finished is False
        assert result.raiders_won is True
        assert result.boss_fight.status is BossFightStatus.FINISHED
        assert result.boss_fight.finished_at == _NOW

        # Каждый рейдер получает +400 // 3 = 133 см.
        per_raider = _INITIAL_BOSS_LENGTH_CM // 3
        assert result.total_granted_cm == per_raider * 3
        for pid in (summoner.id, raider2.id, raider3.id):
            p = await s.players.get_by_id(player_id=pid)
            assert p is not None
            assert p.length.cm == 50 + per_raider

        # Босс: 500 - 400 = 100 ≥ floor; revoked = 400.
        boss_after = await s.players.get_by_id(player_id=boss.id)
        assert boss_after is not None
        assert boss_after.length.cm == boss.length.cm - _INITIAL_BOSS_LENGTH_CM
        assert result.boss_revoked_cm == _INITIAL_BOSS_LENGTH_CM

        # Locks сняты.
        for pid in (summoner.id, raider2.id, raider3.id, boss.id):
            assert ("player", pid) not in s.lock_repo.locks

        # Транзакция коммитится один раз.
        assert s.uow.commits == 1
        assert s.uow.rollbacks == 0

        # Audit-следы: 3 LENGTH_GRANT (рейдеры) + 1 LENGTH_REVOKE (босс)
        # + N SCROLL_DROP + 1 BOSS_FIGHT_FINISHED + 1 BOSS_REWARDS_GRANTED.
        actions = [e.action for e in s.audit.entries]
        assert actions.count(AuditAction.LENGTH_GRANT) == 3
        assert actions.count(AuditAction.LENGTH_REVOKE) == 1
        assert actions.count(AuditAction.BOSS_FIGHT_FINISHED) == 1
        assert actions.count(AuditAction.BOSS_REWARDS_GRANTED) == 1

        # State-transition audit.
        finished_entry = next(
            e for e in s.audit.entries if e.action is AuditAction.BOSS_FIGHT_FINISHED
        )
        assert finished_entry.target_kind == "boss_fight"
        assert finished_entry.target_id == str(fight.id)
        assert finished_entry.idempotency_key == f"boss_fight_finished:{fight.id}"
        assert finished_entry.after is not None
        assert finished_entry.after["raiders_won"] is True
        assert finished_entry.after["status"] == BossFightStatus.FINISHED.value
        assert finished_entry.after["alive_raiders"] == 3

        # Aggregate audit.
        rewards_entry = next(
            e for e in s.audit.entries if e.action is AuditAction.BOSS_REWARDS_GRANTED
        )
        assert rewards_entry.idempotency_key == f"boss_rewards_granted:{fight.id}"
        assert rewards_entry.after is not None
        assert rewards_entry.after["raiders_won"] is True
        assert rewards_entry.after["total_granted_cm"] == per_raider * 3
        assert rewards_entry.after["boss_revoked_cm"] == _INITIAL_BOSS_LENGTH_CM
        assert rewards_entry.after["alive_raiders"] == 3

        # Pending-job-ы отменены (best-effort).
        assert fight.id in s.scheduler.cancelled_boss_round_tick
        assert fight.id in s.scheduler.cancelled_boss_fight_finish

    @pytest.mark.asyncio
    async def test_raider_grant_uses_raid_reward_source(self) -> None:
        """`LENGTH_GRANT` пишется с `source=RAID_REWARD` и idempotency-key."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        grant_entry = next(e for e in s.audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert grant_entry.source is AuditSource.RAID_REWARD
        assert grant_entry.delta_cm == _INITIAL_BOSS_LENGTH_CM
        assert grant_entry.idempotency_key == (
            f"add_length:boss_fight_reward:{fight.id}:{summoner.id}"
        )

    @pytest.mark.asyncio
    async def test_boss_revoke_uses_floor_clamp(self) -> None:
        """Босс с длиной чуть выше floor — revoke кламписится снизу до `victory_threshold_cm`."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        # Босс: 30 см длины, victory_threshold=10, initial=400 → revoke до 10.
        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss", length_cm=30)
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        boss_after = await s.players.get_by_id(player_id=boss.id)
        assert boss_after is not None
        assert boss_after.length.cm == _VICTORY_THRESHOLD_CM
        assert result.boss_revoked_cm == boss.length.cm - _VICTORY_THRESHOLD_CM

        revoke_entry = next(e for e in s.audit.entries if e.action is AuditAction.LENGTH_REVOKE)
        assert revoke_entry.before is not None
        assert revoke_entry.after is not None
        assert revoke_entry.before["length_cm"] == 30
        assert revoke_entry.after["length_cm"] == _VICTORY_THRESHOLD_CM
        assert revoke_entry.delta_cm == -(boss.length.cm - _VICTORY_THRESHOLD_CM)
        assert revoke_entry.idempotency_key == f"boss_fight_loss_revoke:{fight.id}"

    @pytest.mark.asyncio
    async def test_boss_already_at_floor_no_revoke(self) -> None:
        """Если босс уже на floor — `revoked_cm=0`, audit `LENGTH_REVOKE` НЕ пишется."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        # Босс на floor.
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_VICTORY_THRESHOLD_CM,
        )
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.boss_revoked_cm == 0
        actions = [e.action for e in s.audit.entries]
        assert AuditAction.LENGTH_REVOKE not in actions

    @pytest.mark.asyncio
    async def test_scroll_drops_recorded_with_idempotency_keys(self) -> None:
        """`SCROLL_DROP`-эвенты пишутся с правильными idempotency-key-ами."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        raider2 = await _seed_player(s.players, tg_id=_RAIDER_2_TG, username="raider2")
        raider3 = await _seed_player(s.players, tg_id=_RAIDER_3_TG, username="raider3")
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert (
            summoner.id is not None
            and raider2.id is not None
            and raider3.id is not None
            and boss.id is not None
        )
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id, raider2.id, raider3.id),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        # Каждый scroll_drop имеет audit-запись с правильным ключом.
        scroll_entries = [e for e in s.audit.entries if e.action is AuditAction.SCROLL_DROP]
        assert len(scroll_entries) == len(result.scroll_drops)
        for drop, entry in zip(result.scroll_drops, scroll_entries, strict=True):
            scroll_kind = "blessed" if drop.blessed else "regular"
            assert entry.target_kind == "player"
            assert entry.target_id == str(drop.player_id)
            assert entry.idempotency_key == (
                f"boss_scroll_drop:{fight.id}:{drop.player_id}:{scroll_kind}"
            )
            assert entry.after is not None
            assert entry.after["scroll_kind"] == scroll_kind
            assert entry.after["boss_fight_id"] == fight.id

        # Aggregate-counters в BOSS_REWARDS_GRANTED.
        rewards_entry = next(
            e for e in s.audit.entries if e.action is AuditAction.BOSS_REWARDS_GRANTED
        )
        assert rewards_entry.after is not None
        regular_count = sum(1 for d in result.scroll_drops if not d.blessed)
        blessed_count = sum(1 for d in result.scroll_drops if d.blessed)
        assert rewards_entry.after["scroll_drops_regular"] == regular_count
        assert rewards_entry.after["scroll_drops_blessed"] == blessed_count

    @pytest.mark.asyncio
    async def test_scroll_drops_with_p1_blessed_p1_regular(self) -> None:
        """Принудительно `regular=1.0` и `blessed=1.0` → каждому рейдеру оба скролла."""
        s = _build_setup(seed=1)
        # Заменяем balance в use-case через перепресоздание private-поля
        # (Pydantic BaseModel — `model_copy(update=...)`).
        cfg_full = s.use_case._balance
        new_scroll = cfg_full.scroll_drop.model_copy(update={"regular": 1.0, "blessed": 1.0})
        new_bosses = cfg_full.model_copy(update={"scroll_drop": new_scroll})
        s.use_case._balance = new_bosses

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        raider2 = await _seed_player(s.players, tg_id=_RAIDER_2_TG, username="raider2")
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert summoner.id is not None and raider2.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id, raider2.id),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        # 2 рейдера × 2 скролла = 4 drop-а.
        assert len(result.scroll_drops) == 4
        # Сортировка стабильна: per-player сначала regular, затем blessed.
        expected = (
            BossScrollDrop(player_id=summoner.id, blessed=False),
            BossScrollDrop(player_id=summoner.id, blessed=True),
            BossScrollDrop(player_id=raider2.id, blessed=False),
            BossScrollDrop(player_id=raider2.id, blessed=True),
        )
        assert result.scroll_drops == expected
        scroll_entries = [e for e in s.audit.entries if e.action is AuditAction.SCROLL_DROP]
        assert len(scroll_entries) == 4

    @pytest.mark.asyncio
    async def test_scroll_drops_with_p0_zeroes_short_circuited(self) -> None:
        """`regular=0.0` и `blessed=0.0` → ни одного драпа (short-circuit)."""
        s = _build_setup(seed=1)
        cfg_full = s.use_case._balance
        new_scroll = cfg_full.scroll_drop.model_copy(update={"regular": 0.0, "blessed": 0.0})
        new_bosses = cfg_full.model_copy(update={"scroll_drop": new_scroll})
        s.use_case._balance = new_bosses

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.scroll_drops == ()
        scroll_entries = [e for e in s.audit.entries if e.action is AuditAction.SCROLL_DROP]
        assert len(scroll_entries) == 0


# ---------- Happy path: raiders defeated ----------


class TestRaidersDefeat:
    """current_boss_length_cm >= victory_threshold_cm → рейдеры проиграли."""

    @pytest.mark.asyncio
    async def test_boss_wins_grants_sum_of_join_lengths(self) -> None:
        s = _build_setup(seed=1)

        summoner = await _seed_player(
            s.players, tg_id=_SUMMONER_TG, username="summoner", length_cm=70
        )
        raider2 = await _seed_player(
            s.players, tg_id=_RAIDER_2_TG, username="raider2", length_cm=80
        )
        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss", length_cm=200)
        assert summoner.id is not None and raider2.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id, raider2.id),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM + 50,
            raider_length_at_join_cm=100,
        )
        assert fight.id is not None

        for pid in (summoner.id, raider2.id, boss.id):
            await _seed_lock(s.lock_repo, player_id=pid, expires_at=_NOW + timedelta(hours=1))

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.was_already_finished is False
        assert result.raiders_won is False
        assert result.boss_fight.status is BossFightStatus.FINISHED
        # 2 рейдера × 100 см на момент joined = 200.
        assert result.total_granted_cm == 200
        assert result.boss_revoked_cm == 0
        assert result.scroll_drops == ()

        # Босс длиной получил +200.
        boss_after = await s.players.get_by_id(player_id=boss.id)
        assert boss_after is not None
        assert boss_after.length.cm == boss.length.cm + 200

        # Рейдеры — длина не меняется (raider-loss-вычеты вынесены в 3.3-D).
        s_after = await s.players.get_by_id(player_id=summoner.id)
        r2_after = await s.players.get_by_id(player_id=raider2.id)
        assert s_after is not None and r2_after is not None
        assert s_after.length.cm == 70
        assert r2_after.length.cm == 80

        # Locks сняты.
        for pid in (summoner.id, raider2.id, boss.id):
            assert ("player", pid) not in s.lock_repo.locks

        assert s.uow.commits == 1
        assert s.uow.rollbacks == 0

        # Audit: ровно 1 LENGTH_GRANT (босс) + 1 BOSS_FIGHT_FINISHED + 1 BOSS_REWARDS_GRANTED.
        # LENGTH_REVOKE и SCROLL_DROP — НЕТ.
        actions = [e.action for e in s.audit.entries]
        assert actions.count(AuditAction.LENGTH_GRANT) == 1
        assert AuditAction.LENGTH_REVOKE not in actions
        assert AuditAction.SCROLL_DROP not in actions
        assert actions.count(AuditAction.BOSS_FIGHT_FINISHED) == 1
        assert actions.count(AuditAction.BOSS_REWARDS_GRANTED) == 1

        finished_entry = next(
            e for e in s.audit.entries if e.action is AuditAction.BOSS_FIGHT_FINISHED
        )
        assert finished_entry.after is not None
        assert finished_entry.after["raiders_won"] is False

        rewards_entry = next(
            e for e in s.audit.entries if e.action is AuditAction.BOSS_REWARDS_GRANTED
        )
        assert rewards_entry.after is not None
        assert rewards_entry.after["raiders_won"] is False
        assert rewards_entry.after["total_granted_cm"] == 200
        assert rewards_entry.after["boss_revoked_cm"] == 0
        assert rewards_entry.after["scroll_drops_regular"] == 0
        assert rewards_entry.after["scroll_drops_blessed"] == 0

        # Pending-job-ы отменены.
        assert fight.id in s.scheduler.cancelled_boss_round_tick
        assert fight.id in s.scheduler.cancelled_boss_fight_finish

    @pytest.mark.asyncio
    async def test_boss_grant_uses_raid_reward_source(self) -> None:
        """LENGTH_GRANT с `source=RAID_REWARD` и idempotency-key `boss_loss_grant`."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss", length_cm=200)
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM + 50,
            raider_length_at_join_cm=42,
        )
        assert fight.id is not None

        await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        grant_entry = next(e for e in s.audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert grant_entry.source is AuditSource.RAID_REWARD
        assert grant_entry.delta_cm == 42
        assert grant_entry.idempotency_key == f"add_length:boss_loss_grant:{fight.id}"


# ---------- Corner case: empty raider list ----------


class TestEmptyRaiderListCornerCase:
    """Список рейдеров уже пуст (например, все вышли через `LeaveBossLobby`).

    Если current_boss_length_cm < victory_threshold_cm, то всё равно
    «рейдеры победили» — но раздавать награды некому. Босс revoke-ится,
    no scroll-drops.
    """

    @pytest.mark.asyncio
    async def test_no_alive_raiders_with_victory_revokes_boss_only(self) -> None:
        s = _build_setup(seed=1)

        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=999,  # фиктивный, не используется при пустом raider-list-е
            boss_player_id=boss.id,
            raider_player_ids=(),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.raiders_won is True
        assert result.total_granted_cm == 0
        assert result.boss_revoked_cm == _INITIAL_BOSS_LENGTH_CM
        assert result.scroll_drops == ()
        assert result.boss_fight.status is BossFightStatus.FINISHED

        # Никаких LENGTH_GRANT (рейдеров нет).
        actions = [e.action for e in s.audit.entries]
        assert actions.count(AuditAction.LENGTH_GRANT) == 0
        assert actions.count(AuditAction.LENGTH_REVOKE) == 1

    @pytest.mark.asyncio
    async def test_no_alive_raiders_with_defeat_no_grant(self) -> None:
        """Пустой список рейдеров + поражение → ничего не выдаётся."""
        s = _build_setup(seed=1)

        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss", length_cm=200)
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=999,
            boss_player_id=boss.id,
            raider_player_ids=(),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM + 50,
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.raiders_won is False
        assert result.total_granted_cm == 0
        assert result.boss_revoked_cm == 0
        assert result.scroll_drops == ()
        actions = [e.action for e in s.audit.entries]
        assert AuditAction.LENGTH_GRANT not in actions
        assert AuditAction.LENGTH_REVOKE not in actions


# ---------- Idempotency ----------


class TestIdempotency:
    """Повторный вызов на FINISHED/CANCELLED — no-op."""

    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        s = _build_setup(seed=1)

        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss", length_cm=200)
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=999,
            boss_player_id=boss.id,
            status=BossFightStatus.FINISHED,
            raider_player_ids=(),
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert isinstance(result, BossFightFinished)
        assert result.was_already_finished is True
        assert result.raiders_won is None
        assert result.total_granted_cm == 0
        assert result.boss_revoked_cm == 0
        assert result.scroll_drops == ()
        assert result.boss_fight.status is BossFightStatus.FINISHED

        # Никаких mutations / audit / scheduler-cancel-ов.
        assert len(s.audit.entries) == 0
        assert s.uow.commits == 1
        assert s.uow.rollbacks == 0
        assert fight.id not in s.scheduler.cancelled_boss_round_tick
        assert fight.id not in s.scheduler.cancelled_boss_fight_finish

    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        s = _build_setup(seed=1)

        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss")
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=999,
            boss_player_id=boss.id,
            status=BossFightStatus.CANCELLED,
            raider_player_ids=(),
        )
        assert fight.id is not None

        result = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert result.was_already_finished is True
        assert result.raiders_won is None
        assert result.boss_fight.status is BossFightStatus.CANCELLED
        assert len(s.audit.entries) == 0
        assert fight.id not in s.scheduler.cancelled_boss_round_tick

    @pytest.mark.asyncio
    async def test_double_finish_idempotent(self) -> None:
        """Двойной вызов: первый — реальный финиш, второй — no-op."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        boss = await _seed_player(
            s.players,
            tg_id=_BOSS_TG,
            username="boss",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        assert summoner.id is not None and boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=boss.id,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        first = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))
        assert first.was_already_finished is False
        first_audit_count = len(s.audit.entries)
        assert first_audit_count > 0

        second = await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))
        assert second.was_already_finished is True
        # Audit не вырос.
        assert len(s.audit.entries) == first_audit_count


# ---------- Errors ----------


class TestErrors:
    @pytest.mark.asyncio
    async def test_boss_fight_not_found_raises(self) -> None:
        s = _build_setup(seed=1)

        with pytest.raises(BossFightNotFoundError):
            await s.use_case.execute(FinishBossFightInput(boss_fight_id=9999))

        # Транзакция откачена.
        assert s.uow.commits == 0
        assert s.uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_lobby_status_raises_invalid_state(self) -> None:
        """LOBBY → InvalidBossFightStateError (инвариант шедулера нарушен)."""
        s = _build_setup(seed=1)

        boss = await _seed_player(s.players, tg_id=_BOSS_TG, username="boss")
        assert boss.id is not None
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=999,
            boss_player_id=boss.id,
            status=BossFightStatus.LOBBY,
            raider_player_ids=(),
        )
        assert fight.id is not None

        with pytest.raises(InvalidBossFightStateError):
            await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert len(s.audit.entries) == 0
        assert s.uow.commits == 0
        assert s.uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises_on_revoke(self) -> None:
        """Если босс-игрок исчез из БД (не должно быть, но гард есть) → PlayerNotFoundError."""
        s = _build_setup(seed=1)

        summoner = await _seed_player(s.players, tg_id=_SUMMONER_TG, username="summoner")
        assert summoner.id is not None
        # Босса НЕ создаём! Указываем фиктивный boss_player_id.
        fight = await _seed_boss_fight(
            boss_fights=s.boss_fights,
            boss_participants=s.boss_participants,
            summoner_player_id=summoner.id,
            boss_player_id=99999,
            raider_player_ids=(summoner.id,),
            current_boss_length_cm=_VICTORY_THRESHOLD_CM - 1,
        )
        assert fight.id is not None

        with pytest.raises(PlayerNotFoundError):
            await s.use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert s.uow.commits == 0
        assert s.uow.rollbacks == 1
