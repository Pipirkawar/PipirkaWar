"""Тесты сабмишена ходов и AFK-фоллбэка для агрегата `Duel`.

Покрытие:

* **`submit_move`** в IN_PROGRESS — корректная пометка стороны (p1/p2),
  накопление выборов в `pending_round`, авторазрешение раунда при
  готовности обоих, переход к следующему раунду, переход в `COMPLETED`
  после `expected_rounds` раундов.
* **Защитные проверки** — `submit_move` из PENDING_ACCEPT / COMPLETED
  / CANCELLED ⇒ `InvalidDuelStateError`; от неучастника ⇒
  `NotADuelParticipantError`; повторный от того же игрока в текущем
  раунде ⇒ `MoveAlreadySubmittedError`.
* **`force_complete_round`** (AFK-фоллбэк) — заполнение пропущенных
  выборов, разрешение через `resolve_round`, защита от двойного
  применения (`MoveAlreadySubmittedError`), пустой вызов
  (`NoMissingMovesError`).
* **Path-independence** — все 3 раунда используют одни и те же
  снэпшоты длин из `accept`.
* **End-to-end-флоу** — полная 3-раундовая дуэль с проверкой
  `final_outcome` (zero-sum, winner).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelState,
    DuelWinner,
    InvalidDuelStateError,
    MoveAlreadySubmittedError,
    NoMissingMovesError,
    NotADuelParticipantError,
    PendingRound,
    Position,
    RoundChoice,
)

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
_T1 = _NOW + timedelta(minutes=1)
_T2 = _NOW + timedelta(minutes=2)
_T3 = _NOW + timedelta(minutes=3)
_T4 = _NOW + timedelta(minutes=4)


def _started_duel(
    *,
    challenger_id: int = 1,
    challenged_id: int = 2,
    p1_length: int = 100,
    p2_length: int = 100,
    hit_pct: int = 10,
    expected_rounds: int = 3,
) -> Duel:
    return Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=DuelMode.CHAT_ONLY,
        hit_pct=hit_pct,
        expected_rounds=expected_rounds,
        now=_NOW,
    ).accept(
        accepter_id=challenged_id,
        p1_length_cm=p1_length,
        p2_length_cm=p2_length,
        now=_T1,
    )


def _ch(attack: Position, block: Position) -> RoundChoice:
    return RoundChoice(attack=attack, block=block)


class TestSubmitMoveSingleRound:
    def test_first_move_p1(self) -> None:
        d = _started_duel()
        choice = _ch(Position.HIGH, Position.LOW)
        d2 = d.submit_move(player_id=1, choice=choice, now=_T2)
        assert d2.state is DuelState.IN_PROGRESS
        assert d2.pending_round is not None
        assert d2.pending_round.round_num == 1
        assert d2.pending_round.p1_choice == choice
        assert d2.pending_round.p2_choice is None
        assert d2.completed_rounds == ()

    def test_first_move_p2(self) -> None:
        d = _started_duel()
        choice = _ch(Position.MID, Position.MID)
        d2 = d.submit_move(player_id=2, choice=choice, now=_T2)
        assert d2.pending_round is not None
        assert d2.pending_round.p1_choice is None
        assert d2.pending_round.p2_choice == choice

    def test_both_moves_resolve_round(self) -> None:
        d = _started_duel(p1_length=100, p2_length=100, hit_pct=10)
        # p1: HIGH attack, MID block
        # p2: LOW attack, LOW block
        # → p1.attack=HIGH ≠ p2.block=LOW ⇒ p1 hits (10cm to p2)
        # → p2.attack=LOW == p1.block=MID? нет, MID≠LOW ⇒ p2 hits (10cm to p1)
        # Wait: p1.block=MID, p2.attack=LOW, MID != LOW → p2 hits.
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.MID), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        # после 1-го раунда expected_rounds=3, ещё 2 впереди
        assert d.state is DuelState.IN_PROGRESS
        assert len(d.completed_rounds) == 1
        outcome = d.completed_rounds[0]
        assert outcome.p1_attack_blocked is False
        assert outcome.p2_attack_blocked is False
        assert outcome.p1_damage_to_p2 == 10
        assert outcome.p2_damage_to_p1 == 10
        # next pending round is round 2
        assert d.pending_round is not None
        assert d.pending_round.round_num == 2
        assert d.pending_round.p1_choice is None
        assert d.pending_round.p2_choice is None

    def test_round_resolves_with_block(self) -> None:
        d = _started_duel(p1_length=100, p2_length=100, hit_pct=10)
        # обе атаки заблокированы — нулевой урон
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.HIGH, Position.HIGH), now=_T3)
        assert len(d.completed_rounds) == 1
        outcome = d.completed_rounds[0]
        assert outcome.p1_attack_blocked is True
        assert outcome.p2_attack_blocked is True
        assert outcome.p1_damage_to_p2 == 0
        assert outcome.p2_damage_to_p1 == 0

    def test_order_of_submits_doesnt_matter(self) -> None:
        d_a = _started_duel()
        d_a = d_a.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.LOW), now=_T2)
        d_a = d_a.submit_move(player_id=2, choice=_ch(Position.LOW, Position.HIGH), now=_T3)
        d_b = _started_duel()
        d_b = d_b.submit_move(player_id=2, choice=_ch(Position.LOW, Position.HIGH), now=_T2)
        d_b = d_b.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.LOW), now=_T3)
        assert d_a.completed_rounds == d_b.completed_rounds


class TestSubmitMoveErrors:
    def test_submit_in_pending_accept(self) -> None:
        d = Duel.create_challenge(
            challenger_id=1,
            challenged_id=2,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_NOW,
        )
        with pytest.raises(InvalidDuelStateError) as exc:
            d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T1)
        assert exc.value.op == "submit_move"
        assert exc.value.actual is DuelState.PENDING_ACCEPT

    def test_submit_after_cancel(self) -> None:
        d = Duel.create_challenge(
            challenger_id=1,
            challenged_id=2,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_NOW,
        ).cancel(now=_T1)
        with pytest.raises(InvalidDuelStateError):
            d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)

    def test_submit_by_non_participant(self) -> None:
        d = _started_duel()
        with pytest.raises(NotADuelParticipantError) as exc:
            d.submit_move(player_id=99, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        assert exc.value.player_id == 99

    def test_double_submit_same_round_p1(self) -> None:
        d = _started_duel()
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        with pytest.raises(MoveAlreadySubmittedError) as exc:
            d.submit_move(player_id=1, choice=_ch(Position.MID, Position.MID), now=_T3)
        assert exc.value.player_id == 1
        assert exc.value.round_num == 1

    def test_double_submit_same_round_p2(self) -> None:
        d = _started_duel()
        d = d.submit_move(player_id=2, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        with pytest.raises(MoveAlreadySubmittedError) as exc:
            d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        assert exc.value.player_id == 2

    def test_submit_after_completion(self) -> None:
        d = _started_duel(expected_rounds=1)
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        assert d.state is DuelState.COMPLETED
        with pytest.raises(InvalidDuelStateError) as exc:
            d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T4)
        assert exc.value.actual is DuelState.COMPLETED


class TestFullDuelFlow:
    def test_complete_3_round_duel_p1_wins(self) -> None:
        d = _started_duel(p1_length=100, p2_length=100, hit_pct=10)
        # все 3 раунда: p1 атака пробивает, атака p2 блокируется
        # инвариант: p1.attack ≠ p2.block, p1.block == p2.attack
        rounds = [
            (Position.HIGH, Position.LOW, Position.LOW, Position.MID),
            (Position.MID, Position.HIGH, Position.HIGH, Position.LOW),
            (Position.LOW, Position.MID, Position.MID, Position.HIGH),
        ]
        time = _T2
        for i, (p1_atk, p1_blk, p2_atk, p2_blk) in enumerate(rounds):
            time = _T2 + timedelta(seconds=i * 30)
            d = d.submit_move(player_id=1, choice=_ch(p1_atk, p1_blk), now=time)
            d = d.submit_move(player_id=2, choice=_ch(p2_atk, p2_blk), now=time)
        assert d.state is DuelState.COMPLETED
        assert d.completed_at == time
        assert len(d.completed_rounds) == 3
        assert d.pending_round is None
        assert d.final_outcome is not None
        # каждый раунд: p1 пробивает (10cm), p2 — блок (0)
        # → p1 dealt = 30, p2 dealt = 0, deltas: p2 -30, p1 +30
        assert d.final_outcome.p1_total_dealt == 30
        assert d.final_outcome.p2_total_dealt == 0
        assert d.final_outcome.p1_delta_cm == 30
        assert d.final_outcome.p2_delta_cm == -30
        assert d.final_outcome.winner is DuelWinner.P1

    def test_complete_3_round_duel_draw(self) -> None:
        d = _started_duel(p1_length=100, p2_length=100, hit_pct=10)
        # симметричные раунды → ничья
        for i in range(3):
            time = _T2 + timedelta(seconds=i * 30)
            d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.LOW), now=time)
            d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.HIGH), now=time)
        assert d.state is DuelState.COMPLETED
        assert d.final_outcome is not None
        assert d.final_outcome.p1_total_dealt == d.final_outcome.p2_total_dealt
        assert d.final_outcome.winner is DuelWinner.DRAW
        assert d.final_outcome.p1_delta_cm == 0
        assert d.final_outcome.p2_delta_cm == 0

    def test_path_independent_uses_initial_lengths(self) -> None:
        # p1=100cm, p2=20cm. p1 каждый раунд пробивает p2.
        # Урон должен считаться от 20cm (10% = 2) на ВСЕХ раундах,
        # а не от уменьшающейся длины.
        d = _started_duel(p1_length=100, p2_length=20, hit_pct=10)
        for i in range(3):
            time = _T2 + timedelta(seconds=i * 30)
            d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=time)
            d = d.submit_move(player_id=2, choice=_ch(Position.HIGH, Position.LOW), now=time)
        # каждый раунд: p2.attack=HIGH блокируется p1.block=HIGH ⇒ 0
        # p1.attack=HIGH ≠ p2.block=LOW ⇒ p1 пробивает 2cm
        # × 3 раунда = 6cm
        assert d.final_outcome is not None
        assert d.final_outcome.p1_total_dealt == 6
        # Если бы расчёт был path-dependent, после первого раунда p2 был бы 18,
        # потом 16, итог 2+1+1=4. Path-independent даёт 2+2+2=6.
        assert d.final_outcome.p1_total_dealt == 6  # path-independent

    def test_short_duel_one_round(self) -> None:
        d = _started_duel(expected_rounds=1)
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        assert d.state is DuelState.COMPLETED
        assert len(d.completed_rounds) == 1
        assert d.final_outcome is not None
        assert len(d.final_outcome.rounds) == 1

    def test_long_duel_five_rounds(self) -> None:
        d = _started_duel(expected_rounds=5)
        for i in range(5):
            time = _T2 + timedelta(seconds=i * 30)
            d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=time)
            d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=time)
        assert d.state is DuelState.COMPLETED
        assert len(d.completed_rounds) == 5
        assert d.final_outcome is not None
        assert len(d.final_outcome.rounds) == 5


class TestForceCompleteRound:
    def test_fill_missing_p1(self) -> None:
        d = _started_duel(p1_length=100, p2_length=100, hit_pct=10)
        d = d.submit_move(player_id=2, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        # p1 AFK — фоллбэк подставляется снаружи
        d = d.force_complete_round(
            p1_fallback=_ch(Position.LOW, Position.LOW),
            p2_fallback=None,
            now=_T3,
        )
        assert len(d.completed_rounds) == 1
        # p1.attack=LOW vs p2.block=HIGH → не блок → p1 hits
        # p2.attack=HIGH vs p1.block=LOW → не блок → p2 hits
        assert d.completed_rounds[0].p1_damage_to_p2 == 10
        assert d.completed_rounds[0].p2_damage_to_p1 == 10

    def test_fill_missing_p2(self) -> None:
        d = _started_duel()
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.force_complete_round(
            p1_fallback=None,
            p2_fallback=_ch(Position.LOW, Position.HIGH),
            now=_T3,
        )
        assert len(d.completed_rounds) == 1
        assert d.completed_rounds[0].p1_choice == _ch(Position.HIGH, Position.HIGH)
        assert d.completed_rounds[0].p2_choice == _ch(Position.LOW, Position.HIGH)

    def test_fill_both_missing(self) -> None:
        d = _started_duel()
        # никто не отправил — оба AFK
        d = d.force_complete_round(
            p1_fallback=_ch(Position.HIGH, Position.HIGH),
            p2_fallback=_ch(Position.LOW, Position.LOW),
            now=_T3,
        )
        assert len(d.completed_rounds) == 1

    def test_force_complete_after_both_submitted_raises(self) -> None:
        # round автоматически разрешается через submit_move, поэтому
        # force_complete на нём — это попытка фоллбэчить уже не текущий
        # раунд (а следующий, в котором ещё нет ходов). Соответственно
        # должны идти проверки на следующий раунд.
        d = _started_duel(expected_rounds=3)
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        # round 1 авторазрешён, round 2 теперь pending без выборов
        assert d.pending_round is not None
        assert d.pending_round.round_num == 2
        # force_complete без fallback'ов на round 2 (никто не выбрал) → NoMissingMovesError
        # тк p1 и p2 оба None, но fallback'ов тоже нет
        with pytest.raises(NoMissingMovesError):
            d.force_complete_round(p1_fallback=None, p2_fallback=None, now=_T4)

    def test_force_complete_with_extra_fallback_for_already_submitted_p1(self) -> None:
        d = _started_duel()
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        # p1 уже выбрал, нельзя передавать p1_fallback
        with pytest.raises(MoveAlreadySubmittedError) as exc:
            d.force_complete_round(
                p1_fallback=_ch(Position.LOW, Position.LOW),
                p2_fallback=_ch(Position.MID, Position.MID),
                now=_T3,
            )
        assert exc.value.player_id == 1

    def test_force_complete_with_extra_fallback_for_already_submitted_p2(self) -> None:
        d = _started_duel()
        d = d.submit_move(player_id=2, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        with pytest.raises(MoveAlreadySubmittedError) as exc:
            d.force_complete_round(
                p1_fallback=_ch(Position.LOW, Position.LOW),
                p2_fallback=_ch(Position.MID, Position.MID),
                now=_T3,
            )
        assert exc.value.player_id == 2

    def test_force_complete_in_pending_accept(self) -> None:
        d = Duel.create_challenge(
            challenger_id=1,
            challenged_id=2,
            mode=DuelMode.CHAT_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=_NOW,
        )
        with pytest.raises(InvalidDuelStateError):
            d.force_complete_round(
                p1_fallback=_ch(Position.HIGH, Position.HIGH),
                p2_fallback=_ch(Position.LOW, Position.LOW),
                now=_T1,
            )

    def test_force_complete_after_completion(self) -> None:
        d = _started_duel(expected_rounds=1)
        d = d.submit_move(player_id=1, choice=_ch(Position.HIGH, Position.HIGH), now=_T2)
        d = d.submit_move(player_id=2, choice=_ch(Position.LOW, Position.LOW), now=_T3)
        with pytest.raises(InvalidDuelStateError):
            d.force_complete_round(
                p1_fallback=_ch(Position.HIGH, Position.HIGH),
                p2_fallback=_ch(Position.LOW, Position.LOW),
                now=_T4,
            )

    def test_force_complete_advances_to_next_round(self) -> None:
        d = _started_duel(expected_rounds=3)
        d = d.force_complete_round(
            p1_fallback=_ch(Position.HIGH, Position.HIGH),
            p2_fallback=_ch(Position.LOW, Position.LOW),
            now=_T2,
        )
        assert d.state is DuelState.IN_PROGRESS
        assert len(d.completed_rounds) == 1
        assert d.pending_round is not None
        assert d.pending_round.round_num == 2

    def test_force_complete_finishes_duel(self) -> None:
        d = _started_duel(expected_rounds=1)
        d = d.force_complete_round(
            p1_fallback=_ch(Position.HIGH, Position.HIGH),
            p2_fallback=_ch(Position.LOW, Position.LOW),
            now=_T2,
        )
        assert d.state is DuelState.COMPLETED
        assert d.final_outcome is not None


class TestPendingRound:
    def test_is_complete_both_set(self) -> None:
        pr = PendingRound(
            round_num=1,
            p1_choice=_ch(Position.HIGH, Position.HIGH),
            p2_choice=_ch(Position.LOW, Position.LOW),
        )
        assert pr.is_complete is True
        assert pr.has_any_move is True

    def test_is_complete_only_p1(self) -> None:
        pr = PendingRound(
            round_num=1,
            p1_choice=_ch(Position.HIGH, Position.HIGH),
            p2_choice=None,
        )
        assert pr.is_complete is False
        assert pr.has_any_move is True

    def test_is_complete_neither(self) -> None:
        pr = PendingRound(round_num=1, p1_choice=None, p2_choice=None)
        assert pr.is_complete is False
        assert pr.has_any_move is False
