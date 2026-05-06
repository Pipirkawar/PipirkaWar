"""Unit-тесты `ResolveMassDuel` (Спринт 2.2.E)."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest

from pipirik_wars.application.dto.inputs import (
    ResolveMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import (
    MassDuelResolved,
    ResolveMassDuel,
    SubmitMassMove,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuel,
    MassDuelNotFoundError,
    MassDuelNotReadyError,
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
    ResolveMassDuel,
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
    resolve = ResolveMassDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        length_granter=add_length,
        random=rng,
        audit=audit,
        clock=clock,
    )
    return resolve, submit, players, duels, audit, uow, lock_repo, rng, clock


async def _seed_in_progress_duel_2v2(
    *,
    players: FakePlayerRepository,
    duels: FakeMassDuelRepository,
    lock_repo: FakeActivityLockRepository,
    clock: FakeClock,
) -> tuple[MassDuel, int, int, int, int]:
    a1 = await seed_pvp_eligible_player(players, tg_id=1, username="a1", length_cm=50)
    a2 = await seed_pvp_eligible_player(players, tg_id=2, username="a2", length_cm=40)
    d1 = await seed_pvp_eligible_player(players, tg_id=3, username="d1", length_cm=60)
    d2 = await seed_pvp_eligible_player(players, tg_id=4, username="d2", length_cm=30)
    assert a1.id and a2.id and d1.id and d2.id
    duel = MassDuel.create_battle(
        clan1_id=10,
        clan2_id=20,
        clan1_lengths={a1.id: 50, a2.id: 40},
        clan2_lengths={d1.id: 60, d2.id: 30},
        hit_pct=10,
        now=clock.now(),
    )
    saved = await duels.add(duel)
    # Берём locks на всех участников.
    for pid in (a1.id, a2.id, d1.id, d2.id):
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=pid,
            reason=LockReason.PVP,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=30),
        )
    return saved, a1.id, a2.id, d1.id, d2.id


async def _all_submit(
    submit: SubmitMassMove,
    duel_id: int,
    *,
    tg_ids: tuple[int, ...],
    attack: Literal["high", "mid", "low"] = "high",
    block: Literal["high", "mid", "low"] = "mid",
) -> None:
    for tg in tg_ids:
        await submit.execute(
            SubmitMassMoveInput(duel_id=duel_id, tg_id=tg, attack=attack, block=block)
        )


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_resolve_after_all_submitted_completes_and_releases_locks(self) -> None:
        resolve, submit, players, duels, audit, _uow, lock_repo, _rng, _c = _build()
        seeded, a1, a2, d1, d2 = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        await _all_submit(submit, seeded.id, tg_ids=(1, 2, 3, 4))

        result = await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        assert isinstance(result, MassDuelResolved)
        assert result.duel.state is MassDuelState.COMPLETED
        # Локи всех 4 участников сняты.
        for pid in (a1, a2, d1, d2):
            assert ("player", pid) not in lock_repo.locks
        # PVP_MASS_DUEL_COMPLETED записан.
        completed = [e for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_COMPLETED]
        assert len(completed) == 1
        entry = completed[0]
        assert entry.target_id == str(seeded.id)
        assert entry.idempotency_key == f"pvp_mass_duel_completed:{seeded.id}"
        assert entry.after is not None
        assert "afk_fallback" not in entry.after

    @pytest.mark.asyncio
    async def test_resolve_applies_lengths(self) -> None:
        resolve, submit, players, duels, _audit, _uow, lock_repo, _rng, _c = _build()
        seeded, a1, _a2, d1, _d2 = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        # Все атакующие бьют HIGH, защитники блокируют LOW → все удары проходят.
        await _all_submit(submit, seeded.id, tg_ids=(1, 2), attack="high", block="low")
        await _all_submit(submit, seeded.id, tg_ids=(3, 4), attack="high", block="low")
        await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        a1_after = await players.get_by_id(player_id=a1)
        d1_after = await players.get_by_id(player_id=d1)
        assert a1_after is not None
        assert d1_after is not None
        # У атакующих не должна уменьшиться длина (только прибавиться).
        assert a1_after.length.cm >= 50
        # У защитников не должна увеличиться длина (только уменьшиться).
        assert d1_after.length.cm <= 60


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found_raises(self) -> None:
        resolve, *_ = _build()
        with pytest.raises(MassDuelNotFoundError):
            await resolve.execute(ResolveMassDuelInput(duel_id=999))

    @pytest.mark.asyncio
    async def test_resolve_without_all_submits_raises_not_ready(self) -> None:
        resolve, _submit, players, duels, _audit, _uow, lock_repo, _rng, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        with pytest.raises(MassDuelNotReadyError):
            await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))

    @pytest.mark.asyncio
    async def test_resolve_completed_raises_invalid_state(self) -> None:
        resolve, submit, players, duels, *_, lock_repo, _rng, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        await _all_submit(submit, seeded.id, tg_ids=(1, 2, 3, 4))
        await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        # Повторный resolve уже COMPLETED → InvalidMassDuelStateError.
        with pytest.raises(InvalidMassDuelStateError):
            await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))

    @pytest.mark.asyncio
    async def test_resolve_cancelled_raises_invalid_state(self) -> None:
        resolve, _submit, players, duels, *_, lock_repo, _rng, clock = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        cancelled = seeded.cancel(now=clock.now())
        await duels.save(cancelled)
        with pytest.raises(InvalidMassDuelStateError):
            await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
