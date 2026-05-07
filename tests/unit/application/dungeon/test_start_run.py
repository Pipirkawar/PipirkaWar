"""Unit-тесты `StartDungeonRun` (Спринт 3.1-B, ГДД §8).

Зеркало `tests/unit/application/mountains/test_start_run.py`. Различия:
- `LockReason.DUNGEON`, `unlock_levels[\"dungeon\"]=6`, `cooldown ∈ [40, 60]`,
  `max_drops=3`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import StartDungeonRunInput
from pipirik_wars.application.dungeon import (
    DungeonRunStarted,
    StartDungeonRun,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.dungeon import (
    AlreadyInDungeonError,
    DungeonRequirementError,
    DungeonRunStatus,
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
    FakeBalanceConfig,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeDungeonRunRepository,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


def _build_use_case(
    *,
    seed: int = 12345,
    clock: FakeClock | None = None,
) -> tuple[
    StartDungeonRun,
    FakePlayerRepository,
    FakeDungeonRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeRandom,
    FakeActivityLockRepository,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeDungeonRunRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    rng = FakeRandom(seed=seed)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    scheduler = FakeDelayedJobScheduler()
    use_case = StartDungeonRun(
        uow=uow,
        players=players,
        runs=runs,
        locks=locks,
        balance=balance,
        random=rng,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return use_case, players, runs, audit, uow, used_clock, rng, lock_repo, scheduler


async def _seed_eligible_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    username: str = "alice",
    length_cm: int = 100,
    thickness_level: int = 6,
) -> Player:
    """Игрок, удовлетворяющий требованиям входа в данжон (thickness ≥ 6, length ≥ 20)."""
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_creates_in_progress_run_with_outcome(self) -> None:
        use_case, players, runs, _audit, uow, clock, _rng, _locks, scheduler = _build_use_case()
        player = await _seed_eligible_player(players)

        result = await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert isinstance(result, DungeonRunStarted)
        run = result.run
        assert run.id == 1
        assert run.player_id == player.id
        assert run.status is DungeonRunStatus.IN_PROGRESS
        assert run.started_at == clock.now()
        assert run.ends_at == clock.now() + timedelta(minutes=result.cooldown_minutes)
        assert isinstance(run.drops, tuple)
        assert len(run.drops) <= 3  # dungeon: max_drops=3
        assert len(runs.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert scheduler.scheduled_dungeon_finish[run.id].run_at == run.ends_at

    @pytest.mark.asyncio
    async def test_cooldown_in_balance_range(self) -> None:
        use_case, players, _runs, _audit, _uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players)
        balance_dng = build_valid_balance().dungeon

        result = await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert (
            balance_dng.cooldown_min_minutes
            <= result.cooldown_minutes
            <= balance_dng.cooldown_max_minutes
        )

    @pytest.mark.asyncio
    async def test_lock_taken_after_start(self) -> None:
        use_case, players, _runs, _audit, _uow, _clock, _rng, lock_repo, _scheduler = (
            _build_use_case()
        )
        player = await _seed_eligible_player(players)

        await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert player.id is not None
        lock = await lock_repo.get(actor_kind="player", actor_id=player.id)
        assert lock is not None
        assert lock.reason is LockReason.DUNGEON


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_dungeon_run_started(self) -> None:
        use_case, players, _runs, audit, _uow, clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players)

        result = await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.DUNGEON_RUN_STARTED
        assert entry.actor_id == 42
        assert entry.target_kind == "dungeon_run"
        assert entry.target_id == str(result.run.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["player_id"] == result.run.player_id
        assert entry.after["branch_name"] == result.run.branch_name
        assert entry.after["length_delta_cm"] == result.run.length_delta_cm
        assert entry.after["drops_count"] == len(result.run.drops)
        assert entry.after["cooldown_minutes"] == result.cooldown_minutes
        assert entry.after["ends_at"] == result.run.ends_at.isoformat()
        assert entry.idempotency_key == f"dungeon_run_started:{result.run.id}"
        assert entry.occurred_at == clock.now()


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _players, _runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(StartDungeonRunInput(tg_id=42))
        assert exc.value.tg_id == 42
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_required_raises(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players, thickness_level=5)  # требует ≥6

        with pytest.raises(DungeonRequirementError) as exc:
            await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 6
        assert exc.value.actual == 5
        assert runs.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_length_below_min_raises(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players, length_cm=15)  # < 20 см

        with pytest.raises(DungeonRequirementError) as exc:
            await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert exc.value.requirement == "length"
        assert exc.value.required == 20
        assert exc.value.actual == 15
        assert runs.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_double_start_raises_already_in_dungeon(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        player = await _seed_eligible_player(players)

        await use_case.execute(StartDungeonRunInput(tg_id=42))
        with pytest.raises(AlreadyInDungeonError) as exc:
            await use_case.execute(StartDungeonRunInput(tg_id=42))

        assert player.id is not None
        assert exc.value.player_id == player.id
        assert len(runs.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 1
        assert len(audit.entries) == 1
