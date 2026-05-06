"""Integration-тесты для AFK-таймера масс-боя (Спринт 2.2.F).

Проверяет, что use-case-ы `StartMassDuel` / `ResolveMassDuel` /
`ForceResolveMassDuel` / `CancelMassDuel` корректно вызывают
`schedule_mass_duel_afk_resolution(...)` и `cancel_mass_duel_afk_resolution(...)`
у `IDelayedJobScheduler`, и что без шедулера use-case-ы продолжают работать
(`scheduler=None` — back-compat для тестов / dev-режима).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest

from pipirik_wars.application.dto.inputs import (
    CancelMassDuelInput,
    ForceResolveMassDuelInput,
    ResolveMassDuelInput,
    StartMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import (
    CancelMassDuel,
    ForceResolveMassDuel,
    ResolveMassDuel,
    StartMassDuel,
    SubmitMassMove,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import MassDuel
from pipirik_wars.domain.security import LockReason
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeIdempotencyKey,
    FakeMassDuelRepository,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.application.pvp._mass_helpers import (
    MASS_NOW,
    seed_clan,
    seed_eligible_clan_member,
)
from tests.unit.domain.balance.factories import build_valid_balance


def _build_balance() -> FakeBalanceConfig:
    return FakeBalanceConfig(build_valid_balance())


def _build_clock() -> FakeClock:
    return FakeClock(MASS_NOW)


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


class TestStartMassDuelScheduler:
    @pytest.mark.asyncio
    async def test_schedules_afk_timer_at_now_plus_move_timer(self) -> None:
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        clans = FakeClanRepository()
        members = FakeClanMembershipRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        balance = _build_balance()
        scheduler = FakeDelayedJobScheduler()
        use_case = StartMassDuel(
            uow=uow,
            clans=clans,
            clan_members=members,
            players=players,
            duels=duels,
            locks=locks,
            balance=balance,
            audit=audit,
            clock=clock,
            scheduler=scheduler,
        )
        attacker = await seed_clan(clans, chat_id=-100, title="A")
        defender = await seed_clan(clans, chat_id=-200, title="D")
        assert attacker.id is not None and defender.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=attacker.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defender.id, tg_id=2, username="d"
        )

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )
        assert result.duel.id is not None
        # Один scheduled job на duel.id, run_at = now + move_timer_seconds (180 по умолчанию).
        assert result.duel.id in scheduler.scheduled_mass_duel_afk
        job = scheduler.scheduled_mass_duel_afk[result.duel.id]
        assert job.duel_id == result.duel.id
        assert job.run_at == MASS_NOW + timedelta(seconds=180)
        assert scheduler.cancelled_mass_duel_afk == []

    @pytest.mark.asyncio
    async def test_no_scheduler_does_not_break(self) -> None:
        # Back-compat: scheduler=None — use-case всё равно работает.
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        clans = FakeClanRepository()
        members = FakeClanMembershipRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        balance = _build_balance()
        use_case = StartMassDuel(
            uow=uow,
            clans=clans,
            clan_members=members,
            players=players,
            duels=duels,
            locks=locks,
            balance=balance,
            audit=audit,
            clock=clock,
        )
        attacker = await seed_clan(clans, chat_id=-100, title="A")
        defender = await seed_clan(clans, chat_id=-200, title="D")
        assert attacker.id is not None and defender.id is not None
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=attacker.id, tg_id=1
        )
        await seed_eligible_clan_member(
            players=players, clan_members=members, clan_id=defender.id, tg_id=2, username="d"
        )

        result = await use_case.execute(
            StartMassDuelInput(
                initiator_tg_id=1,
                attacker_chat_id=-100,
                defender_chat_id=-200,
            )
        )
        assert result.duel.id is not None  # без scheduler всё равно работает


class TestResolveMassDuelScheduler:
    @pytest.mark.asyncio
    async def test_cancels_afk_timer_after_resolve(self) -> None:
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        scheduler = FakeDelayedJobScheduler()
        balance = _build_balance()
        rng = FakeRandom()
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
            scheduler=scheduler,
        )
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        # Эмулируем шедулер: сначала "запланируем" таймер вручную.
        await scheduler.schedule_mass_duel_afk_resolution(
            duel_id=seeded.id, run_at=clock.now() + timedelta(seconds=180)
        )
        await _all_submit(submit, seeded.id, tg_ids=(1, 2, 3, 4))

        await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        assert seeded.id in scheduler.cancelled_mass_duel_afk
        assert seeded.id not in scheduler.scheduled_mass_duel_afk


class TestForceResolveMassDuelScheduler:
    @pytest.mark.asyncio
    async def test_cancels_afk_timer_after_force_resolve(self) -> None:
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        scheduler = FakeDelayedJobScheduler()
        balance = _build_balance()
        rng = FakeRandom()
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
        force = ForceResolveMassDuel(
            uow=uow,
            players=players,
            duels=duels,
            locks=locks,
            length_granter=add_length,
            random=rng,
            audit=audit,
            clock=clock,
            scheduler=scheduler,
        )
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        await scheduler.schedule_mass_duel_afk_resolution(
            duel_id=seeded.id, run_at=clock.now() + timedelta(seconds=180)
        )

        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is False
        assert seeded.id in scheduler.cancelled_mass_duel_afk

    @pytest.mark.asyncio
    async def test_no_op_when_already_resolved_still_no_cancel(self) -> None:
        # Идемпотентный no-op: scheduler не дёргается (use-case вышел до cancel).
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        scheduler = FakeDelayedJobScheduler()
        balance = _build_balance()
        rng = FakeRandom()
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
            scheduler=scheduler,
        )
        force = ForceResolveMassDuel(
            uow=uow,
            players=players,
            duels=duels,
            locks=locks,
            length_granter=add_length,
            random=rng,
            audit=audit,
            clock=clock,
            scheduler=scheduler,
        )
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        await _all_submit(submit, seeded.id, tg_ids=(1, 2, 3, 4))
        await resolve.execute(ResolveMassDuelInput(duel_id=seeded.id))
        # Сбросим cancelled_*, чтобы наблюдать только следующий вызов.
        scheduler.cancelled_mass_duel_afk.clear()

        result = await force.execute(ForceResolveMassDuelInput(duel_id=seeded.id))
        assert result.was_already_resolved is True
        # No-op-ветка возвращает раньше, чем доходит до cancel.
        assert scheduler.cancelled_mass_duel_afk == []


class TestCancelMassDuelScheduler:
    @pytest.mark.asyncio
    async def test_cancels_afk_timer_after_cancel(self) -> None:
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        scheduler = FakeDelayedJobScheduler()
        cancel = CancelMassDuel(
            uow=uow,
            duels=duels,
            locks=locks,
            audit=audit,
            clock=clock,
            scheduler=scheduler,
        )
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        await scheduler.schedule_mass_duel_afk_resolution(
            duel_id=seeded.id, run_at=clock.now() + timedelta(seconds=180)
        )

        result = await cancel.execute(CancelMassDuelInput(duel_id=seeded.id, reason="admin"))
        assert result.was_already_cancelled is False
        assert seeded.id in scheduler.cancelled_mass_duel_afk
        assert seeded.id not in scheduler.scheduled_mass_duel_afk

    @pytest.mark.asyncio
    async def test_idempotent_already_cancelled_does_not_call_scheduler(self) -> None:
        # was_already_cancelled=True → no-op-ветка возвращает раньше, чем cancel.
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        duels = FakeMassDuelRepository()
        audit = FakeAuditLogger()
        clock = _build_clock()
        lock_repo = FakeActivityLockRepository()
        locks = ActivityLockService(repository=lock_repo, clock=clock)
        scheduler = FakeDelayedJobScheduler()
        cancel = CancelMassDuel(
            uow=uow,
            duels=duels,
            locks=locks,
            audit=audit,
            clock=clock,
            scheduler=scheduler,
        )
        seeded, *_ = await _seed_in_progress_duel_2v2(
            players=players, duels=duels, lock_repo=lock_repo, clock=clock
        )
        assert seeded.id is not None
        await cancel.execute(CancelMassDuelInput(duel_id=seeded.id, reason="r1"))
        scheduler.cancelled_mass_duel_afk.clear()

        result = await cancel.execute(CancelMassDuelInput(duel_id=seeded.id, reason="r2"))
        assert result.was_already_cancelled is True
        assert scheduler.cancelled_mass_duel_afk == []
