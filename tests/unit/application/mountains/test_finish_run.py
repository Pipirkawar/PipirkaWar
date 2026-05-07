"""Unit-тесты `FinishMountainRun` (Спринт 3.1-B).

Покрытие:
- happy gain: длина начислена через `ILengthGranter` (audit `LENGTH_GRANT`),
  лок снят, audit `MOUNTAIN_RUN_FINISHED` пишется, UoW коммитит ровно 1 раз;
- happy loss: длина списана через прямой `Player.with_length` + audit
  `LENGTH_REVOKE` (delta_cm < 0), лок снят, статус `FINISHED`;
- zero-delta (если внезапно случится — picker гарантирует ≠0): не пишется
  ни `LENGTH_GRANT`, ни `LENGTH_REVOKE`, но `MOUNTAIN_RUN_FINISHED` пишется;
- идемпотентность: повторный финиш на уже-`FINISHED`-записи — no-op
  (никаких mutations / audit-записей кроме `commit`);
- `MountainRunNotFoundError`, если по `run_id` нет записи в `mountain_runs`;
- `PlayerNotFoundError`, если ссылка на игрока «висит»;
- loss не уводит длину ниже 0 (clamped к 0).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import FinishMountainRunInput
from pipirik_wars.application.mountains import (
    FinishMountainRun,
    MountainRunFinished,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.mountains import (
    MountainRun,
    MountainRunNotFoundError,
    MountainRunStatus,
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
    FakeIdempotencyKey,
    FakeMountainRunRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_STARTED = _NOW - timedelta(minutes=30)
_ENDS = _NOW


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    FinishMountainRun,
    FakePlayerRepository,
    FakeMountainRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeMountainRunRepository()
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
    use_case = FinishMountainRun(
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
    length_cm: int = 100,
    thickness_level: int = 3,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value="alice"), now=_STARTED)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_STARTED).with_length(
        Length(cm=length_cm), now=_STARTED
    )
    return await players.save(upgraded)


async def _seed_run(
    runs: FakeMountainRunRepository,
    *,
    player_id: int,
    branch_name: str = "normal_gain",
    length_delta_cm: int = 10,
    drops: tuple[PveItemDrop, ...] = (),
) -> MountainRun:
    run = MountainRun(
        id=None,
        player_id=player_id,
        status=MountainRunStatus.IN_PROGRESS,
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
        reason=LockReason.MOUNTAINS,
        acquired_at=_STARTED,
        expires_at=expires_at,
    )


class TestHappyPathGain:
    @pytest.mark.asyncio
    async def test_grants_length_and_releases_lock(self) -> None:
        use_case, players, runs, audit, uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=100)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=15,
            branch_name="normal_gain",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishMountainRunInput(run_id=run.id))

        assert isinstance(result, MountainRunFinished)
        assert result.was_already_finished is False
        assert result.player_after.length.cm == 100 + 15
        assert result.run.status is MountainRunStatus.FINISHED
        assert result.run.finished_at == _NOW
        assert lock_repo.locks.get(("player", player.id)) is None
        assert uow.commits == 1
        assert uow.rollbacks == 0
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.MOUNTAIN_RUN_FINISHED in actions
        length_entry = next(e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert length_entry.source is AuditSource.MOUNTAINS
        assert length_entry.idempotency_key == f"add_length:mountain_run:{run.id}"
        assert length_entry.delta_cm == 15
        finish_entry = next(
            e for e in audit.entries if e.action is AuditAction.MOUNTAIN_RUN_FINISHED
        )
        assert finish_entry.idempotency_key == f"mountain_run_finished:{run.id}"
        assert finish_entry.target_id == str(run.id)


class TestHappyPathLoss:
    @pytest.mark.asyncio
    async def test_revokes_length_directly_for_loss(self) -> None:
        use_case, players, runs, audit, uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=100)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=-12,
            branch_name="heavy_loss",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishMountainRunInput(run_id=run.id))

        assert result.was_already_finished is False
        assert result.player_after.length.cm == 100 - 12
        assert result.run.status is MountainRunStatus.FINISHED
        assert lock_repo.locks.get(("player", player.id)) is None
        assert uow.commits == 1
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_REVOKE in actions
        assert AuditAction.LENGTH_GRANT not in actions
        revoke_entry = next(e for e in audit.entries if e.action is AuditAction.LENGTH_REVOKE)
        assert revoke_entry.source is AuditSource.MOUNTAINS
        assert revoke_entry.idempotency_key == f"mountain_run_loss_revoke:{run.id}"
        assert revoke_entry.delta_cm == -12
        assert revoke_entry.before == {"length_cm": 100}
        assert revoke_entry.after == {"length_cm": 88}

    @pytest.mark.asyncio
    async def test_loss_clamps_length_at_zero(self) -> None:
        # Игрок с 25 см получает loss=-50 — длина должна clamp-нуться к 0.
        use_case, players, runs, _audit, _uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, length_cm=25)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=-50,
            branch_name="heavy_loss",
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishMountainRunInput(run_id=run.id))

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

        result = await use_case.execute(FinishMountainRunInput(run_id=run.id))

        assert result.was_already_finished is True
        assert result.player_before == result.player_after
        assert audit.entries == []
        assert uow.commits == 1
        assert uow.rollbacks == 0


class TestErrors:
    @pytest.mark.asyncio
    async def test_run_not_found_raises(self) -> None:
        use_case, _players, _runs, audit, uow, _clock, _lock_repo = _build_use_case()

        with pytest.raises(MountainRunNotFoundError) as exc:
            await use_case.execute(FinishMountainRunInput(run_id=999))

        assert exc.value.run_id == 999
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _players, runs, _audit, uow, _clock, _lock_repo = _build_use_case()
        # seed run без соответствующего игрока
        run = await _seed_run(runs, player_id=999)
        assert run.id is not None

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(FinishMountainRunInput(run_id=run.id))

        assert uow.commits == 0
        assert uow.rollbacks == 1
