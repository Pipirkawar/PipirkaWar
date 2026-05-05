"""Unit-тесты `SubmitMove` (Спринт 2.1.D).

Покрытие:

- happy path mid-duel: ход не закрывает раунд → состояние IN_PROGRESS;
- happy path mid-round (закрывает раунд, но не дуэль): pending_round
  переключается на следующий, длины ещё не применены;
- happy path final round → COMPLETED + apply_duel_outcome:
  победителю прибавили длину через `AddLength` (audit `LENGTH_GRANT`,
  source=`PVP_REWARD`); проигравшему вычли (audit `LENGTH_REVOKE`);
  оба лока сняты;
- ничья → ни добавления, ни вычета, audit `PVP_DUEL_COMPLETED` пишется;
- error-кейсы: дуэль не найдена; игрок не найден; не участник;
  повторный submit на одном раунде; не в IN_PROGRESS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import SubmitMoveInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.pvp import MoveSubmitted, SubmitMove
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    DuelWinner,
    InvalidDuelStateError,
    MoveAlreadySubmittedError,
    NotADuelParticipantError,
    Position,
    RoundChoice,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction, AuditSource
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
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_EARLIER = _NOW - timedelta(minutes=2)


def _build() -> tuple[
    SubmitMove,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeClock,
]:
    use_case, players, duels, audit, uow, lock_repo, clock, _scheduler = _build_full()
    return use_case, players, duels, audit, uow, lock_repo, clock


def _build_full() -> tuple[
    SubmitMove,
    FakePlayerRepository,
    FakeDuelRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeActivityLockRepository,
    FakeClock,
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
    use_case = SubmitMove(
        uow=uow,
        players=players,
        duels=duels,
        locks=locks,
        length_granter=length_granter,
        audit=audit,
        clock=clock,
        balance=balance,
        scheduler=scheduler,
    )
    return use_case, players, duels, audit, uow, lock_repo, clock, scheduler


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


def _hit_choice() -> RoundChoice:
    """`attack=HIGH`, `block=LOW` — гарантированный hit (block != attack)."""
    return RoundChoice(attack=Position.HIGH, block=Position.LOW)


def _draw_choice() -> RoundChoice:
    """`attack=HIGH`, `block=HIGH` — заблокированный удар."""
    return RoundChoice(attack=Position.HIGH, block=Position.HIGH)


class TestPartialRound:
    @pytest.mark.asyncio
    async def test_first_choice_does_not_close_round(self) -> None:
        use_case, players, duels, audit, uow, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(
            duels,
            challenger_id=p1.id,
            challenged_id=p2.id,
            p1_length_cm=p1.length.cm,
            p2_length_cm=p2.length.cm,
        )
        assert duel.id is not None

        result = await use_case.execute(
            SubmitMoveInput(
                duel_id=duel.id,
                tg_id=1,
                attack="high",
                block="low",
            )
        )

        assert isinstance(result, MoveSubmitted)
        assert result.duel_completed is False
        assert result.duel.state is DuelState.IN_PROGRESS
        assert result.duel.pending_round is not None
        assert result.duel.pending_round.round_num == 1
        assert result.duel.pending_round.p1_choice == _hit_choice()
        assert result.duel.pending_round.p2_choice is None
        assert audit.entries == []
        assert uow.commits == 1


class TestRoundResolves:
    @pytest.mark.asyncio
    async def test_second_choice_advances_to_next_round(self) -> None:
        use_case, players, duels, audit, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        # p1 уже выбрал
        first = duel.submit_move(player_id=p1.id, choice=_hit_choice(), now=_EARLIER)
        await duels.save(first)

        result = await use_case.execute(
            SubmitMoveInput(
                duel_id=duel.id,
                tg_id=2,
                attack="high",
                block="mid",
            )
        )

        assert result.duel_completed is False
        # round 1 закрыт, round 2 открыт
        assert len(result.duel.completed_rounds) == 1
        assert result.duel.pending_round is not None
        assert result.duel.pending_round.round_num == 2
        # длины ещё не применены — audit пуст
        assert audit.entries == []


class TestDuelCompletes:
    async def _play_first_two_rounds(
        self,
        duel: Duel,
        duels: FakeDuelRepository,
        *,
        p1_id: int,
        p2_id: int,
    ) -> Duel:
        # round 1: p1 hits, p2 blocks (draw on damage)
        s1 = duel.submit_move(player_id=p1_id, choice=_hit_choice(), now=_EARLIER)
        s2 = s1.submit_move(player_id=p2_id, choice=_hit_choice(), now=_EARLIER)
        # round 2: тоже двусторонний hit
        s3 = s2.submit_move(player_id=p1_id, choice=_hit_choice(), now=_EARLIER)
        s4 = s3.submit_move(player_id=p2_id, choice=_hit_choice(), now=_EARLIER)
        await duels.save(s4)
        return s4

    @pytest.mark.asyncio
    async def test_winner_gets_length_loser_loses(self) -> None:
        use_case, players, duels, audit, _u, lock_repo, _c = _build()
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
        # доигрываем до 3-го раунда
        d2 = await self._play_first_two_rounds(duel, duels, p1_id=p1.id, p2_id=p2.id)
        # p1 ходит первым в финальном раунде — атака LOW, блок HIGH;
        # p2 (через use-case) — атака HIGH, блок HIGH (блочит свой удар).
        # Итого p1 побеждает по dealt-у.
        round3_p1 = d2.submit_move(
            player_id=p1.id,
            choice=RoundChoice(attack=Position.LOW, block=Position.HIGH),
            now=_EARLIER,
        )
        await duels.save(round3_p1)
        # последний ход — через use-case
        result = await use_case.execute(
            SubmitMoveInput(
                duel_id=duel.id,
                tg_id=2,
                attack="high",
                block="high",  # блочит свой high → p1.attack high blocked
            )
        )

        # p1 выиграл (hit X 2 раунда от p2 в раунде 1+2; раунд 3 — p1 hit
        # low не блочен, p2 hit high заблочен)
        assert result.duel_completed is True
        assert result.duel.state is DuelState.COMPLETED
        outcome = result.duel.final_outcome
        assert outcome is not None
        assert outcome.winner is DuelWinner.P1
        # zero-sum
        assert outcome.p1_delta_cm + outcome.p2_delta_cm == 0
        # p1 получил длины, p2 потерял
        assert outcome.p1_delta_cm > 0
        assert outcome.p2_delta_cm < 0

        # длины применены к игрокам
        p1_after = await players.get_by_id(player_id=p1.id)
        p2_after = await players.get_by_id(player_id=p2.id)
        assert p1_after is not None
        assert p2_after is not None
        assert p1_after.length.cm == 50 + outcome.p1_delta_cm
        assert p2_after.length.cm == 40 + outcome.p2_delta_cm

        # лок снят с обеих сторон
        assert ("player", p1.id) not in lock_repo.locks
        assert ("player", p2.id) not in lock_repo.locks

        # audit:
        # - LENGTH_GRANT (через AddLength для победителя)
        # - LENGTH_REVOKE (для проигравшего)
        # - PVP_DUEL_COMPLETED (системное)
        # суммарно 3 записи
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.LENGTH_REVOKE in actions
        assert AuditAction.PVP_DUEL_COMPLETED in actions
        # источник прибавки — PVP_REWARD
        grant = next(e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert grant.source is AuditSource.PVP_REWARD
        # idempotency-ключи различны для p1/p2
        revoke = next(e for e in audit.entries if e.action is AuditAction.LENGTH_REVOKE)
        assert revoke.idempotency_key == f"pvp_duel_loss_revoke:{duel.id}:p2"

    @pytest.mark.asyncio
    async def test_draw_no_length_changes(self) -> None:
        use_case, players, duels, audit, _u, lock_repo, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        await _seed_locks(lock_repo, challenger_id=p1.id, challenged_id=p2.id)

        # все 3 раунда: оба блочат свою атаку → 0 dealt с обеих сторон.
        prev = duel
        for _ in range(2):
            prev = prev.submit_move(player_id=p1.id, choice=_draw_choice(), now=_EARLIER)
            prev = prev.submit_move(player_id=p2.id, choice=_draw_choice(), now=_EARLIER)
        # 3-й раунд: p1 ставит выбор → save → p2 ходит через use-case
        prev = prev.submit_move(player_id=p1.id, choice=_draw_choice(), now=_EARLIER)
        await duels.save(prev)

        result = await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=2, attack="high", block="high")
        )
        assert result.duel_completed is True
        outcome = result.duel.final_outcome
        assert outcome is not None
        assert outcome.winner is DuelWinner.DRAW
        assert outcome.p1_delta_cm == 0
        assert outcome.p2_delta_cm == 0
        # длины не менялись
        p1_after = await players.get_by_id(player_id=p1.id)
        p2_after = await players.get_by_id(player_id=p2.id)
        assert p1_after is not None
        assert p2_after is not None
        assert p1_after.length.cm == 50
        assert p2_after.length.cm == 40
        # ни LENGTH_GRANT, ни LENGTH_REVOKE
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT not in actions
        assert AuditAction.LENGTH_REVOKE not in actions
        # PVP_DUEL_COMPLETED — есть
        assert AuditAction.PVP_DUEL_COMPLETED in actions


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found(self) -> None:
        use_case, players, _d, _a, uow, _l, _c = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        with pytest.raises(DuelNotFoundError):
            await use_case.execute(
                SubmitMoveInput(duel_id=999, tg_id=1, attack="high", block="low")
            )
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, players, duels, _a, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                SubmitMoveInput(duel_id=duel.id, tg_id=999, attack="high", block="low")
            )

    @pytest.mark.asyncio
    async def test_not_a_participant(self) -> None:
        use_case, players, duels, _a, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        third = await seed_pvp_eligible_player(players, tg_id=3, username="carol")
        assert p1.id is not None
        assert p2.id is not None
        assert third.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        with pytest.raises(NotADuelParticipantError):
            await use_case.execute(
                SubmitMoveInput(duel_id=duel.id, tg_id=3, attack="high", block="low")
            )

    @pytest.mark.asyncio
    async def test_double_submit_in_same_round(self) -> None:
        use_case, players, duels, _a, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=1, attack="high", block="low")
        )
        with pytest.raises(MoveAlreadySubmittedError):
            await use_case.execute(
                SubmitMoveInput(duel_id=duel.id, tg_id=1, attack="mid", block="high")
            )

    @pytest.mark.asyncio
    async def test_not_in_progress_state(self) -> None:
        use_case, players, duels, _a, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        # PENDING_ACCEPT — не IN_PROGRESS
        pending = Duel.create_challenge(
            challenger_id=p1.id,
            challenged_id=p2.id,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_EARLIER,
        )
        saved = await duels.add(pending)
        assert saved.id is not None
        with pytest.raises(InvalidDuelStateError):
            await use_case.execute(
                SubmitMoveInput(duel_id=saved.id, tg_id=1, attack="high", block="low")
            )


class TestRoundAfkTimer:
    """Спринт 2.1.G: SubmitMove дёргает AFK-таймер раунда.

    Алгоритм (см. submit_move.py):
    - партиал-ход (раунд не закрылся) → scheduler не дёргается;
    - раунд закрылся, дуэль ещё IN_PROGRESS → cancel предыдущего + schedule следующего;
    - раунд закрылся, дуэль COMPLETED → cancel последнего раунда, новый не ставится.
    """

    @pytest.mark.asyncio
    async def test_partial_round_does_not_touch_scheduler(self) -> None:
        use_case, players, duels, _a, _u, _l, _c, scheduler = _build_full()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=1, attack="high", block="low")
        )

        assert scheduler.scheduled_round_afk == {}
        assert scheduler.cancelled_round_afk == []

    @pytest.mark.asyncio
    async def test_closing_round_mid_duel_cancels_prev_and_schedules_next(self) -> None:
        use_case, players, duels, _a, _u, _l, _c, scheduler = _build_full()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None
        # p1 уже выбрал в раунде 1 — его submit-ом второй игрок закроет раунд.
        first = duel.submit_move(player_id=p1.id, choice=_hit_choice(), now=_EARLIER)
        await duels.save(first)

        await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=2, attack="high", block="mid")
        )

        # Cancel раунда 1 + schedule раунда 2.
        assert (duel.id, 1) in scheduler.cancelled_round_afk
        assert (duel.id, 2) in scheduler.scheduled_round_afk
        scheduled = scheduler.scheduled_round_afk[(duel.id, 2)]
        assert scheduled.round_num == 2
        assert scheduled.run_at == _NOW + timedelta(seconds=45)

    @pytest.mark.asyncio
    async def test_closing_final_round_cancels_prev_only(self) -> None:
        """Если раунд закрывает дуэль (COMPLETED) — следующий не планируется."""
        use_case, players, duels, _a, _u, lock_repo, _c, scheduler = _build_full()
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
        # Доигрываем до 3-го раунда: 2 завершённых + p1 уже сходил в 3-м.
        s1 = duel.submit_move(player_id=p1.id, choice=_hit_choice(), now=_EARLIER)
        s2 = s1.submit_move(player_id=p2.id, choice=_hit_choice(), now=_EARLIER)
        s3 = s2.submit_move(player_id=p1.id, choice=_hit_choice(), now=_EARLIER)
        s4 = s3.submit_move(player_id=p2.id, choice=_hit_choice(), now=_EARLIER)
        s5 = s4.submit_move(player_id=p1.id, choice=_hit_choice(), now=_EARLIER)
        await duels.save(s5)
        assert s5.pending_round is not None
        assert s5.pending_round.round_num == 3

        result = await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=2, attack="high", block="low")
        )

        assert result.duel_completed is True
        # Cancel раунда 3, новый не ставится.
        assert (duel.id, 3) in scheduler.cancelled_round_afk
        assert scheduler.scheduled_round_afk == {}

    @pytest.mark.asyncio
    async def test_no_scheduler_no_op(self) -> None:
        """Если scheduler не подвязан — use-case работает без таймера."""
        use_case, players, duels, _a, _u, _l, _c = _build()
        p1 = await seed_pvp_eligible_player(players, tg_id=1, length_cm=50)
        p2 = await seed_pvp_eligible_player(players, tg_id=2, length_cm=40, username="bob")
        assert p1.id is not None
        assert p2.id is not None
        duel = await _seed_in_progress_duel(duels, challenger_id=p1.id, challenged_id=p2.id)
        assert duel.id is not None

        result = await use_case.execute(
            SubmitMoveInput(duel_id=duel.id, tg_id=1, attack="high", block="low")
        )
        assert result.duel_completed is False
