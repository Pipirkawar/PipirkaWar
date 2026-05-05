"""Unit-тесты `ResolveAfkRound` (Спринт 2.1.D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import ResolveAfkRoundInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import AfkRoundResolved, ResolveAfkRound
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    Position,
    RoundChoice,
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
    FakeDelayedJobScheduler,
    FakeDuelRepository,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=2)


def _build(
    *,
    seed: int = 12345,
) -> tuple[
    ResolveAfkRound,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeRandom,
]:
    use_case, players, duels, audit, uow, lock_repo, rng, _scheduler = _build_full(seed=seed)
    return use_case, players, duels, audit, uow, lock_repo, rng


def _build_full(
    *,
    seed: int = 12345,
) -> tuple[
    ResolveAfkRound,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeRandom,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeDuelRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance = FakeBalanceConfig(build_valid_balance())
    rng = FakeRandom(seed=seed)
    scheduler = FakeDelayedJobScheduler()
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = ResolveAfkRound(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        length_granter=length_granter,
        random=rng,
        audit=audit,
        clock=clock,
        balance=balance,
        scheduler=scheduler,
    )
    return use_case, players, duels, audit, uow, lock_repo, rng, scheduler


async def _seed_in_progress_duel(
    duels: FakeDuelRepository,
    *,
    challenger_id: int,
    challenged_id: int,
    p1_length_cm: int = 50,
    p2_length_cm: int = 40,
) -> Duel:
    pending = Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=DuelMode.CHAT_ONLY,
        hit_pct=10,
        expected_rounds=3,
        now=_EARLIER,
    )
    accepted = pending.accept(
        accepter_id=challenged_id,
        p1_length_cm=p1_length_cm,
        p2_length_cm=p2_length_cm,
        now=_EARLIER,
    )
    return await duels.add(accepted)


async def _seed_locks(
    lock_repo: FakeActivityLockRepository,
    *,
    challenger_id: int,
    challenged_id: int,
) -> None:
    for player_id in (challenger_id, challenged_id):
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=player_id,
            reason=LockReason.PVP,
            now=_EARLIER,
            expires_at=_NOW + timedelta(minutes=30),
        )


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_both_afk_rolls_random_and_advances(self) -> None:
        use_case, players, duels, audit, uow, _l, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))

        assert isinstance(result, AfkRoundResolved)
        assert result.was_already_resolved is False
        assert result.duel_completed is False
        # round 1 закрыт, round 2 открыт
        assert len(result.duel.completed_rounds) == 1
        assert result.duel.pending_round is not None
        assert result.duel.pending_round.round_num == 2
        # выборы случайны, но обязательно из {HIGH, MID, LOW}
        completed = result.duel.completed_rounds[0]
        assert completed.p1_choice.attack in {Position.HIGH, Position.MID, Position.LOW}
        assert completed.p2_choice.attack in {Position.HIGH, Position.MID, Position.LOW}
        assert uow.commits == 1
        # audit пуст: длины не применяются (дуэль не завершилась)
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_p1_picked_p2_afk_only_p2_rolled(self) -> None:
        use_case, players, duels, _audit, _uow, _l, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        # p1 уже выбрал HIGH/LOW
        choice = RoundChoice(attack=Position.HIGH, block=Position.LOW)
        afterp1 = duel.submit_move(player_id=p1.id, choice=choice, now=_EARLIER)
        await duels.save(afterp1)

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))

        assert result.was_already_resolved is False
        # p1 сохранил свой выбор
        completed = result.duel.completed_rounds[0]
        assert completed.p1_choice == choice

    @pytest.mark.asyncio
    async def test_completes_final_round_applies_length(self) -> None:
        use_case, players, duels, audit, _u, lock_repo, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(
            duels,
            challenger_id=p1.id,
            challenged_id=p2.id,
            p1_length_cm=50,
            p2_length_cm=40,
        )
        assert duel.id is not None
        await _seed_locks(lock_repo, challenger_id=p1.id, challenged_id=p2.id)

        # сыграли 2 раунда вручную (двусторонний hit)
        hit = RoundChoice(attack=Position.HIGH, block=Position.LOW)
        d1 = duel.submit_move(player_id=p1.id, choice=hit, now=_EARLIER)
        d2 = d1.submit_move(player_id=p2.id, choice=hit, now=_EARLIER)
        d3 = d2.submit_move(player_id=p1.id, choice=hit, now=_EARLIER)
        d4 = d3.submit_move(player_id=p2.id, choice=hit, now=_EARLIER)
        await duels.save(d4)

        # никто не сходил в раунде 3 → AFK резолв
        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=3))

        assert result.duel_completed is True
        assert result.duel.state is DuelState.COMPLETED
        outcome = result.duel.final_outcome
        assert outcome is not None
        # zero-sum
        assert outcome.p1_delta_cm + outcome.p2_delta_cm == 0
        # лок снят с обоих
        assert ("player", p1.id) not in lock_repo.locks
        assert ("player", p2.id) not in lock_repo.locks
        # audit содержит PVP_DUEL_COMPLETED
        actions = [e.action for e in audit.entries]
        assert AuditAction.PVP_DUEL_COMPLETED in actions
        # afk_fallback=True для аудита
        completed_entry = next(
            e for e in audit.entries if e.action is AuditAction.PVP_DUEL_COMPLETED
        )
        assert completed_entry.after is not None
        assert completed_entry.after.get("afk_fallback") is True

    @pytest.mark.asyncio
    async def test_deterministic_rolls_for_seeded_random(self) -> None:
        # При одинаковом seed-е — два инстанса дают идентичный результат.
        async def _run(seed: int) -> tuple[Position, Position]:
            use_case, players, duels, _audit, _u, _l, _rng = _build(seed=seed)
            p1 = await seed_pvp_eligible_player(players, tg_id=1)
            p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
            assert p1.id is not None
            assert p2.id is not None
            duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
            assert duel.id is not None
            r = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))
            completed = r.duel.completed_rounds[0]
            return completed.p1_choice.attack, completed.p2_choice.attack

        r1 = await _run(42)
        r2 = await _run(42)
        assert r1 == r2


class TestIdempotencyAndStaleTimers:
    @pytest.mark.asyncio
    async def test_round_already_resolved_is_noop(self) -> None:
        # Раунд 1 уже сыгран реальными ходами; шедулер опоздал.
        use_case, players, duels, audit, _u, _l, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        hit = RoundChoice(attack=Position.HIGH, block=Position.LOW)
        d1 = duel.submit_move(player_id=p1.id, choice=hit, now=_EARLIER)
        d2 = d1.submit_move(player_id=p2.id, choice=hit, now=_EARLIER)
        await duels.save(d2)
        # round 2 уже идёт — таймер 1 пришёл «постфактум»
        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))
        assert result.was_already_resolved is True
        # ничего не менялось
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_duel_already_terminal_is_noop(self) -> None:
        use_case, players, duels, audit, _u, _l, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        # CANCELLED state
        pending = Duel.create_challenge(
            challenger_id=p1.id,
            challenged_id=p2.id,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_EARLIER,
        )
        cancelled = pending.cancel(now=_EARLIER)
        saved = await duels.add(cancelled)
        assert saved.id is not None
        result = await use_case.execute(ResolveAfkRoundInput(duel_id=saved.id, round_num=1))
        assert result.was_already_resolved is True
        assert audit.entries == []


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found(self) -> None:
        use_case, _p, _d, _a, uow, _l, _rng = _build()
        with pytest.raises(DuelNotFoundError):
            await use_case.execute(ResolveAfkRoundInput(duel_id=999, round_num=1))
        assert uow.rollbacks == 1


class TestRoundAfkTimerScheduling:
    """Спринт 2.1.G: после force_complete_round планируется таймер
    следующего раунда (если дуэль не завершилась)."""

    @pytest.mark.asyncio
    async def test_schedules_next_round_timer_when_duel_continues(self) -> None:
        use_case, players, duels, _audit, _uow, _l, _rng, scheduler = _build_full()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))

        assert result.duel_completed is False
        assert (duel.id, 2) in scheduler.scheduled_round_afk
        scheduled = scheduler.scheduled_round_afk[(duel.id, 2)]
        assert scheduled.round_num == 2
        assert scheduled.run_at == _NOW + timedelta(seconds=45)

    @pytest.mark.asyncio
    async def test_no_schedule_when_duel_completed(self) -> None:
        use_case, players, duels, _a, _u, lock_repo, _rng, scheduler = _build_full()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(
            duels,
            challenger_id=p1.id,
            challenged_id=p2.id,
            p1_length_cm=50,
            p2_length_cm=40,
        )
        assert duel.id is not None
        await _seed_locks(lock_repo, challenger_id=p1.id, challenged_id=p2.id)
        # доигрываем 2 раунда вручную; на 3-м обоих afk-роллим
        s1 = duel.submit_move(
            player_id=p1.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            now=_EARLIER,
        )
        s2 = s1.submit_move(
            player_id=p2.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            now=_EARLIER,
        )
        s3 = s2.submit_move(
            player_id=p1.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            now=_EARLIER,
        )
        s4 = s3.submit_move(
            player_id=p2.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            now=_EARLIER,
        )
        await duels.save(s4)
        assert s4.pending_round is not None
        assert s4.pending_round.round_num == 3

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=3))

        assert result.duel_completed is True
        assert scheduler.scheduled_round_afk == {}

    @pytest.mark.asyncio
    async def test_stale_timer_no_op_does_not_reschedule(self) -> None:
        """Если pending.round_num не совпал с input — без планирования (idempotent)."""
        use_case, players, duels, _a, _u, _l, _rng, scheduler = _build_full()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        # Раунд 1 уже закрыт реальными ходами — input указывает на старый раунд.
        s1 = duel.submit_move(
            player_id=p1.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            now=_EARLIER,
        )
        s2 = s1.submit_move(
            player_id=p2.id,
            choice=RoundChoice(attack=Position.HIGH, block=Position.MID),
            now=_EARLIER,
        )
        await duels.save(s2)

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))
        assert result.was_already_resolved is True
        assert scheduler.scheduled_round_afk == {}

    @pytest.mark.asyncio
    async def test_no_scheduler_no_op(self) -> None:
        """Без scheduler-а use-case работает (back-compat для теста D-spec)."""
        use_case, players, duels, _a, _u, _l, _rng = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        result = await use_case.execute(ResolveAfkRoundInput(duel_id=duel.id, round_num=1))
        assert result.duel_completed is False
