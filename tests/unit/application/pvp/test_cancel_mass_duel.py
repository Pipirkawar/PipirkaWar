"""Unit-тесты `CancelMassDuel` (Спринт 2.2.E)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from pipirik_wars.application.dto.inputs import (
    CancelMassDuelInput,
    ResolveMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import (
    CancelMassDuel,
    MassDuelCancelled,
    ResolveMassDuel,
    SubmitMassMove,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
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
    CancelMassDuel,
    FakePlayerRepository,
    FakeMassDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeMassDuelRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(MASS_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    use_case = CancelMassDuel(
        uow=uow,
        duels=duels,
        locks=locks,
        audit=audit,
        clock=clock,
    )
    return use_case, players, duels, audit, uow, lock_repo, clock


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
    async def test_cancel_in_progress_releases_locks_and_audits(self) -> None:
        use_case, players, duels, audit, uow, lock_repo, _c = _build()
        seeded, a1, a2, d1, d2 = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        result = await use_case.execute(
            CancelMassDuelInput(duel_id=seeded.id, reason="admin_cancel")
        )
        assert isinstance(result, MassDuelCancelled)
        assert result.was_already_cancelled is False
        assert result.duel.state is MassDuelState.CANCELLED
        # Локи всех 4 участников сняты.
        for pid in (a1, a2, d1, d2):
            assert ("player", pid) not in lock_repo.locks
        # Audit запись.
        cancelled_entries = [
            e for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_CANCELLED
        ]
        assert len(cancelled_entries) == 1
        entry = cancelled_entries[0]
        assert entry.target_kind == "pvp_mass_duel"
        assert entry.target_id == str(seeded.id)
        assert entry.idempotency_key == f"pvp_mass_duel_cancelled:{seeded.id}"
        assert entry.reason == "admin_cancel"
        assert entry.before == {"state": "in_progress"}
        assert entry.after == {"state": "cancelled"}
        assert uow.commits == 1


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_double_cancel_returns_already_cancelled(self) -> None:
        use_case, players, duels, audit, _uow, lock_repo, _c = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=_c
        )
        assert seeded.id is not None
        await use_case.execute(CancelMassDuelInput(duel_id=seeded.id, reason="r1"))
        result = await use_case.execute(CancelMassDuelInput(duel_id=seeded.id, reason="r2"))
        assert result.was_already_cancelled is True
        # Audit-запись только одна (повторная отмена — no-op).
        cancelled_count = sum(
            1 for e in audit.entries if e.action is AuditAction.PVP_MASS_DUEL_CANCELLED
        )
        assert cancelled_count == 1


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found_raises(self) -> None:
        use_case, *_ = _build()
        with pytest.raises(MassDuelNotFoundError):
            await use_case.execute(CancelMassDuelInput(duel_id=999, reason="r"))

    @pytest.mark.asyncio
    async def test_cancel_completed_raises_invalid_state(self) -> None:
        use_case, players, duels, audit, uow, lock_repo, clock = _build()
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None

        # Резолвим через ResolveMassDuel.
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
        rng = FakeRandom()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
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
        for tg in (1, 2, 3, 4):
            await submit.execute(
                SubmitMassMoveInput(duel_id=seeded.id, tg_id=tg, attack="high", block="mid")
            )
        await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        # Теперь cancel должен бросить.
        with pytest.raises(InvalidMassDuelStateError):
            await use_case.execute(CancelMassDuelInput(duel_id=seeded.id, reason="r"))
