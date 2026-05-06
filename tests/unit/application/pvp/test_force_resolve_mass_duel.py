"""Unit-тесты `ForceResolveMassDuel` (Спринт 2.2.E)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from pipirik_wars.application.dto.inputs import (
    ForceResolveMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import (
    ForceResolveMassDuel,
    MassDuelForceResolved,
    SubmitMassMove,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import (
    MassDuel,
    MassDuelNotFoundError,
    MassDuelState,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakeMassDuelRepository,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.application.pvp._mass_helpers import MASS_NOW
from tests.unit.domain.balance.factories import build_valid_balance


def _build() -> tuple[
    ForceResolveMassDuel,
    SubmitMassMove,
    FakePlayerRepository,
    FakeMassDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeRandom,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeMassDuelRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(MASS_NOW)
    rng = FakeRandom()
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    add_length = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    submit = SubmitMassMove(uow=uow, players=players, duels=duels, clock=clock)
    force = ForceResolveMassDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        length_granter=add_length,
        random=rng,
        audit=audit,
        clock=clock,
    )
    return force, submit, players, duels, audit, uow, lock_repo, rng, clock


async def _seed_in_progress_duel_2v2(
    *,
    players: FakePlayerRepository,
    duels: FakeMassDuelRepository,
    lock_repo: FakeActivityLockRepository,
    clock: FakeClock,
) -> tuple[MassDuel, int, int, int, int]:
    a1 = await seed_pvp_eligible_player(players, tg_id=1, username="a1")
    a2 = await seed_pvp_eligible_player(players, tg_id=2, username="a2")
    d1 = await seed_pvp_eligible_player(players, tg_id=3, username="d1")
    d2 = await seed_pvp_eligible_player(players, tg_id=4, username="d2")
    assert a1.id and a2.id and d1.id and d2.id
    duel = MassDuel.create_battle(
        clan1_id=10,
        clan2_id=20,
        clan1_lengths={a1.id: 50, a2.id: 50},
        clan2_lengths={d1.id: 50, d2.id: 50},
        hit_pct=10,
        now=clock.now(),
    )
    saved = await duels.add(duel)
    for pid in (a1.id, a2.id, d1.id, d2.id):
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=pid,
            reason=LockReason.PVP,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=30),
        )
    return saved, a1.id, a2.id, d1.id, d2.id


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_no_one_submitted_force_resolves_with_random_choices(self) -> None:
        force, _submit, players, duels, audit, _uow, lock_repo, _rng, _c = _build()
        seeded, a1, a2, d1, d2 = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert isinstance(result, MassDuelForceResolved)
        assert result.was_already_resolved is False
        assert result.duel.state is MassDuelState.COMPLETED
        # Локи сняты.
        for pid in (a1, a2, d1, d2):
            assert ("player", pid) not in lock_repo.locks
        # Audit с afk_fallback=True.
        completed = [e for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_COMPLETED]
        assert len(completed) == 1
        assert completed[0].after is not None
        assert completed[0].after.get("afk_fallback") is True
        assert completed[0].reason == "pvp_mass_duel_completed_afk"

    @pytest.mark.asyncio
    async def test_partial_submission_force_resolves(self) -> None:
        force, submit, players, duels, _audit, _uow, lock_repo, _rng, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        # Только 2 из 4 отправили.
        await submit.execute(
            SubmitMassMoveInput(duel_id=seeded.id, tg_id=1, attack="high", block="mid")
        )
        await submit.execute(
            SubmitMassMoveInput(duel_id=seeded.id, tg_id=3, attack="mid", block="high")
        )
        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is False
        assert result.duel.state is MassDuelState.COMPLETED

    @pytest.mark.asyncio
    async def test_all_submitted_resolves_without_force_submit_step(self) -> None:
        force, submit, players, duels, _audit, _uow, lock_repo, _rng, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        for tg in (1, 2, 3, 4):
            await submit.execute(
                SubmitMassMoveInput(duel_id=seeded.id, tg_id=tg, attack="high", block="mid")
            )
        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is False
        assert result.duel.state is MassDuelState.COMPLETED


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_completed_is_no_op(self) -> None:
        force, _submit, players, duels, audit, _uow, lock_repo, _rng, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        # Первый force-резолв.
        await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        completed_count_after_first = sum(
            1 for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_COMPLETED
        )
        # Повторный — no-op.
        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is True
        completed_count_after_second = sum(
            1 for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_COMPLETED
        )
        # Audit не дублируется.
        assert completed_count_after_first == completed_count_after_second

    @pytest.mark.asyncio
    async def test_already_cancelled_is_no_op(self) -> None:
        force, _submit, players, duels, _audit, _uow, lock_repo, _rng, clock = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        cancelled = seeded.cancel(now=clock.now())
        await duels.save(cancelled)
        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is True
        assert result.duel.state is MassDuelState.CANCELLED


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found_raises(self) -> None:
        force, *_ = _build()
        with pytest.raises(MassDuelNotFoundError):
            await force.execute(ForceResolveMassDuelInput(duel_id=999))
