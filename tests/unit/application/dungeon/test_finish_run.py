"""Unit-тесты `FinishDungeonRun` (Спринт 3.1-B).

Зеркало `tests/unit/application/mountains/test_finish_run.py`. Различия:
- `AuditAction.DUNGEON_RUN_*`, `AuditSource.DUNGEON`, idempotency_key-и
  с префиксом `dungeon_run_*`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import FinishDungeonRunInput
from pipirik_wars.application.dungeon import (
    DungeonRunFinished,
    FinishDungeonRun,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunNotFoundError,
    DungeonRunStatus,
    PveItemDrop,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
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
    FakeClock,
    FakeDungeonRunRepository,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_STARTED = _NOW - timedelta(minutes=50)
_ENDS = _NOW


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    FinishDungeonRun,
    FakePlayerRepository,
    FakeDungeonRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeDungeonRunRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=FakeBalanceConfig(build_valid_balance()),
        clock=used_clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = FinishDungeonRun(
        uow=uow,
        players=players,
        runs=runs,
        locks=locks,
        length_granter=length_granter,
        audit=audit,
        clock=used_clock,
    )
    return use_case, players, runs, audit, uow, used_clock, lock_repo


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    length_cm: int = 200,
    thickness_level: int = 6,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value="alice"), now=_STARTED)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_STARTED).with_length(
        Length(cm=length_cm), now=_STARTED
    )
    return await players.save(upgraded)


async def _seed_run(
    runs: FakeDungeonRunRepository,
    *,
    player_id: int,
    branch_name: str = "normal_gain",
    length_delta_cm: int = 30,
    drops: tuple[PveItemDrop, ...] = (),
) -> DungeonRun:
    run = DungeonRun(
        id=None,
        player_id=player_id,
        status=DungeonRunStatus.IN_PROGRESS,
        started_at=_STARTED,
        ends_at=_ENDS,
        branch_name=branch_name,
        length_delta_cm=length_delta_cm,
        drops=drops,
        finished_at=None,
    )
    return await runs.add(run)


async def _seed_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    expires_at: datetime,
) -> None:
    lock_repo.locks[("player", player_id)] = ActivityLock(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.DUNGEON,
        acquired_at=_STARTED,
        expires_at=expires_at,
    )


class TestHappyPathGain:
    @pytest.mark.asyncio
    async def test_grants_length_and_releases_lock(self) -> None:
        use_case, players, runs, audit, uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=200)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=25,
            branch_name="normal_gain",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishDungeonRunInput(run_id=run.id))

        assert isinstance(result, DungeonRunFinished)
        assert result.was_already_finished is False
        assert result.player_after.length.cm == 200 + 25
        assert result.run.status is DungeonRunStatus.FINISHED
        assert result.run.finished_at == _NOW
        assert lock_repo.locks.get(("player", player.id)) is None
        assert uow.commits == 1
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.DUNGEON_RUN_FINISHED in actions
        length_entry = next(e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert length_entry.source is AuditSource.DUNGEON
        assert length_entry.idempotency_key == f"add_length:dungeon_run:{run.id}"
        assert length_entry.delta_cm == 25
        finish_entry = next(
            e for e in audit.entries if e.action is AuditAction.DUNGEON_RUN_FINISHED
        )
        assert finish_entry.idempotency_key == f"dungeon_run_finished:{run.id}"


class TestHappyPathLoss:
    @pytest.mark.asyncio
    async def test_revokes_length_directly_for_loss(self) -> None:
        use_case, players, runs, audit, uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=200)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=-30,
            branch_name="heavy_loss",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishDungeonRunInput(run_id=run.id))

        assert result.was_already_finished is False
        assert result.player_after.length.cm == 170
        assert result.run.status is DungeonRunStatus.FINISHED
        assert lock_repo.locks.get(("player", player.id)) is None
        assert uow.commits == 1
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_REVOKE in actions
        assert AuditAction.LENGTH_GRANT not in actions
        revoke_entry = next(e for e in audit.entries if e.action is AuditAction.LENGTH_REVOKE)
        assert revoke_entry.source is AuditSource.DUNGEON
        assert revoke_entry.idempotency_key == f"dungeon_run_loss_revoke:{run.id}"
        assert revoke_entry.delta_cm == -30

    @pytest.mark.asyncio
    async def test_loss_clamps_length_at_zero(self) -> None:
        use_case, players, runs, _audit, _uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=25)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=-100,
            branch_name="heavy_loss",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishDungeonRunInput(run_id=run.id))

        assert result.player_after.length.cm == 0


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        use_case, players, runs, audit, uow, _clock, _lock_repo = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        run = await _seed_run(runs, player_id=player.id)
        assert run.id is not None
        runs.rows[0] = run.mark_finished(finished_at=_STARTED)

        result = await use_case.execute(FinishDungeonRunInput(run_id=run.id))

        assert result.was_already_finished is True
        assert result.player_before == result.player_after
        assert audit.entries == []
        assert uow.commits == 1


class TestErrors:
    @pytest.mark.asyncio
    async def test_run_not_found_raises(self) -> None:
        use_case, _players, _runs, audit, uow, _clock, _lock_repo = _build_use_case()

        with pytest.raises(DungeonRunNotFoundError) as exc:
            await use_case.execute(FinishDungeonRunInput(run_id=999))

        assert exc.value.run_id == 999
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _players, runs, _audit, uow, _clock, _lock_repo = _build_use_case()
        run = await _seed_run(runs, player_id=999)
        assert run.id is not None

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(FinishDungeonRunInput(run_id=run.id))

        assert uow.commits == 0
        assert uow.rollbacks == 1
