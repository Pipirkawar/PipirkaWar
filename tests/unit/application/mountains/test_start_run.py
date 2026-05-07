"""Unit-тесты `StartMountainRun` (Спринт 3.1-B, ГДД §8).

Покрытие:
- happy path: cooldown ∈ [mountains.cooldown_min_minutes, ...max_minutes],
  создаётся `IN_PROGRESS`-запись с уже сролленым исходом
  (`branch_name`/`length_delta_cm`/`drops`), audit пишется, finish-job
  запланирован, UoW коммитит ровно 1 раз;
- `MountainsRequirementError(requirement="thickness")` — недостаточный
  уровень (`thickness < unlock_levels.mountains`);
- `MountainsRequirementError(requirement="length")` — длина < 20 см
  (правило 20 см, ГДД §3.1);
- `AlreadyInMountainsError` при попытке стартовать второй активный поход;
- `PlayerNotFoundError` если игрока нет в `users`;
- audit-запись содержит ключевые поля и правильный idempotency_key;
- detерминизм при фиксированном seed → идентичный outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import StartMountainRunInput
from pipirik_wars.application.mountains import (
    MountainRunStarted,
    StartMountainRun,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.mountains import (
    AlreadyInMountainsError,
    MountainRunStatus,
    MountainsRequirementError,
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
    FakeMountainRunRepository,
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
    StartMountainRun,
    FakePlayerRepository,
    FakeMountainRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeRandom,
    FakeActivityLockRepository,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeMountainRunRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    rng = FakeRandom(seed=seed)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    scheduler = FakeDelayedJobScheduler()
    use_case = StartMountainRun(
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
    length_cm: int = 50,
    thickness_level: int = 3,
) -> Player:
    """Игрок, удовлетворяющий требованиям входа в горы (thickness ≥ 3, length ≥ 20)."""
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

        result = await use_case.execute(StartMountainRunInput(tg_id=42))

        assert isinstance(result, MountainRunStarted)
        run = result.run
        assert run.id == 1
        assert run.player_id == player.id
        assert run.status is MountainRunStatus.IN_PROGRESS
        assert run.started_at == clock.now()
        assert run.ends_at == clock.now() + timedelta(minutes=result.cooldown_minutes)
        assert run.branch_name in {
            "scarce_gain",
            "normal_gain",
            "abundant_gain",
            "scarce_loss",
            "heavy_loss",
        }
        assert -1000 < run.length_delta_cm < 1000
        assert isinstance(run.drops, tuple)
        assert len(run.drops) <= 1  # mountains: max_drops=1
        assert len(runs.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # finish-job запланирован на ends_at
        assert scheduler.scheduled_mountain_finish[run.id].run_at == run.ends_at

    @pytest.mark.asyncio
    async def test_cooldown_in_balance_range(self) -> None:
        use_case, players, _runs, _audit, _uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players)
        balance_mtn = build_valid_balance().mountains

        result = await use_case.execute(StartMountainRunInput(tg_id=42))

        assert (
            balance_mtn.cooldown_min_minutes
            <= result.cooldown_minutes
            <= balance_mtn.cooldown_max_minutes
        )

    @pytest.mark.asyncio
    async def test_lock_taken_after_start(self) -> None:
        use_case, players, _runs, _audit, _uow, _clock, _rng, lock_repo, _scheduler = (
            _build_use_case()
        )
        player = await _seed_eligible_player(players)

        await use_case.execute(StartMountainRunInput(tg_id=42))

        assert player.id is not None
        lock = await lock_repo.get(actor_kind="player", actor_id=player.id)
        assert lock is not None
        assert lock.reason is LockReason.MOUNTAINS

    @pytest.mark.asyncio
    async def test_loss_branch_allowed_for_player_above_min_length(self) -> None:
        # Loss-исход допустим: правило 20 см работает только на ВХОДЕ в горы.
        # После применения loss-а длина может опуститься ниже 20 см
        # (clamped к 0 в FinishMountainRun) — это by design (см. PvP).
        for seed in range(1, 50):
            use_case, players, _runs, _audit, _uow, _clock, _rng, _lock_repo, _scheduler = (
                _build_use_case(seed=seed)
            )
            await _seed_eligible_player(players)
            result = await use_case.execute(StartMountainRunInput(tg_id=42))
            if result.run.branch_name.endswith("_loss"):
                assert result.run.length_delta_cm < 0
                return
        pytest.fail("loss branch never rolled in 50 seeds — balance regression?")


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_mountain_run_started(self) -> None:
        use_case, players, _runs, audit, _uow, clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players)

        result = await use_case.execute(StartMountainRunInput(tg_id=42))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.MOUNTAIN_RUN_STARTED
        assert entry.actor_id == 42
        assert entry.target_kind == "mountain_run"
        assert entry.target_id == str(result.run.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["player_id"] == result.run.player_id
        assert entry.after["branch_name"] == result.run.branch_name
        assert entry.after["length_delta_cm"] == result.run.length_delta_cm
        assert entry.after["drops_count"] == len(result.run.drops)
        assert entry.after["cooldown_minutes"] == result.cooldown_minutes
        assert entry.after["ends_at"] == result.run.ends_at.isoformat()
        assert entry.idempotency_key == f"mountain_run_started:{result.run.id}"
        assert entry.occurred_at == clock.now()


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _players, _runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(StartMountainRunInput(tg_id=42))
        assert exc.value.tg_id == 42
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_required_raises(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players, thickness_level=2)  # mountains требует ≥3

        with pytest.raises(MountainsRequirementError) as exc:
            await use_case.execute(StartMountainRunInput(tg_id=42))

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 3
        assert exc.value.actual == 2
        assert runs.rows == []
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_length_below_min_raises(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        await _seed_eligible_player(players, length_cm=19)  # < 20 см

        with pytest.raises(MountainsRequirementError) as exc:
            await use_case.execute(StartMountainRunInput(tg_id=42))

        assert exc.value.requirement == "length"
        assert exc.value.required == 20
        assert exc.value.actual == 19
        assert runs.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_double_start_raises_already_in_mountains(self) -> None:
        use_case, players, runs, audit, uow, _clock, _rng, _locks, _scheduler = _build_use_case()
        player = await _seed_eligible_player(players)

        await use_case.execute(StartMountainRunInput(tg_id=42))
        with pytest.raises(AlreadyInMountainsError) as exc:
            await use_case.execute(StartMountainRunInput(tg_id=42))

        assert player.id is not None
        assert exc.value.player_id == player.id
        assert len(runs.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 1
        assert len(audit.entries) == 1


class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_seed_same_outcome(self) -> None:
        first: MountainRunStarted | None = None
        second: MountainRunStarted | None = None
        for slot in (0, 1):
            use_case, players, _runs, _audit, _uow, _clock, _rng, _locks, _scheduler = (
                _build_use_case(seed=99)
            )
            await _seed_eligible_player(players, tg_id=100 + slot)
            result = await use_case.execute(StartMountainRunInput(tg_id=100 + slot))
            if slot == 0:
                first = result
            else:
                second = result
        assert first is not None and second is not None
        assert first.cooldown_minutes == second.cooldown_minutes
        assert first.run.branch_name == second.run.branch_name
        assert first.run.length_delta_cm == second.run.length_delta_cm
        assert first.run.drops == second.run.drops
