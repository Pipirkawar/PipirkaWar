"""Тесты движка полного 3-раундового PvP-боя 1×1 (`resolve_duel`).

Покрытие:

* **Z-sum инвариант**: `p1_delta_cm + p2_delta_cm == 0` всегда.
* **Стандартные сценарии**: чистая победа p1 (3 пробития), ничья (одинаковый
  суммарный dealt), смешанный обмен.
* **`InvalidRoundCountError`** — `len(rounds) ≠ expected_rounds`.
* **Path-independent** — разный порядок одних и тех же выборов даёт
  одинаковую дельту (так и должно быть, длины не меняются между раундами).
* **`expected_rounds`-параметр** — движок поддерживает короткие/длинные дуэли.

Тесты — чистые, без БД и моков.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.pvp import (
    DuelWinner,
    InvalidRoundCountError,
    Position,
    RoundChoice,
    resolve_duel,
)


def _ch(attack: Position, block: Position) -> RoundChoice:
    return RoundChoice(attack, block)


class TestDuelWinnerScenarios:
    """Стандартные исходы 3-раундовой дуэли."""

    def test_p1_full_sweep_3_hits_unblocked(self) -> None:
        # Все 3 раунда p1 атакует HIGH, p2 блокирует MID — все 3 пробития.
        # p2 атакует LOW, p1 блокирует LOW — все 3 заблокировано.
        # Длины 100/100, hit_pct=10 ⇒ p1 дилит 30, p2 дилит 0.
        rounds = [
            (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID)),
            (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID)),
            (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID)),
        ]
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.winner == DuelWinner.P1
        assert out.p1_total_dealt == 30
        assert out.p2_total_dealt == 0
        assert out.p1_delta_cm == 30
        assert out.p2_delta_cm == -30

    def test_p2_wins_when_more_dealt(self) -> None:
        # Симметричный случай: p2 пробивает 3, p1 блокирует 3 ⇒ p2 wins.
        rounds = [
            (_ch(Position.LOW, Position.MID), _ch(Position.HIGH, Position.LOW)),
            (_ch(Position.LOW, Position.MID), _ch(Position.HIGH, Position.LOW)),
            (_ch(Position.LOW, Position.MID), _ch(Position.HIGH, Position.LOW)),
        ]
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.winner == DuelWinner.P2
        assert out.p2_total_dealt == 30
        assert out.p1_delta_cm == -30
        assert out.p2_delta_cm == 30

    def test_draw_when_equal_dealt(self) -> None:
        # Симметричный обмен: оба пробивают одинаково в каждом раунде.
        # p1.atk=HIGH vs p2.blk=LOW → пробитие. p2.atk=HIGH vs p1.blk=LOW → пробитие.
        rounds = [
            (_ch(Position.HIGH, Position.LOW), _ch(Position.HIGH, Position.LOW)),
            (_ch(Position.HIGH, Position.LOW), _ch(Position.HIGH, Position.LOW)),
            (_ch(Position.HIGH, Position.LOW), _ch(Position.HIGH, Position.LOW)),
        ]
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.winner == DuelWinner.DRAW
        assert out.p1_total_dealt == 30
        assert out.p2_total_dealt == 30
        assert out.p1_delta_cm == 0
        assert out.p2_delta_cm == 0

    def test_draw_when_no_hits(self) -> None:
        # Все 3 раунда обе атаки полностью заблокированы.
        rounds = [
            (_ch(Position.HIGH, Position.HIGH), _ch(Position.HIGH, Position.HIGH)),
            (_ch(Position.MID, Position.MID), _ch(Position.MID, Position.MID)),
            (_ch(Position.LOW, Position.LOW), _ch(Position.LOW, Position.LOW)),
        ]
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.winner == DuelWinner.DRAW
        assert out.p1_total_dealt == 0
        assert out.p2_total_dealt == 0

    def test_mixed_win_with_partial_exchange(self) -> None:
        # Смешанный сценарий с разной длиной: p1=120, p2=50, hit_pct=10
        # Раунд 1: p1.atk=HIGH vs p2.blk=MID (пробитие, dmg=5); p2.atk=MID vs p1.blk=HIGH (пробитие, dmg=12)
        # Раунд 2: p1.atk=MID vs p2.blk=MID (блок, dmg=0); p2.atk=MID vs p1.blk=MID (блок, dmg=0)
        # Раунд 3: p1.atk=LOW vs p2.blk=HIGH (пробитие, dmg=5); p2.atk=HIGH vs p1.blk=LOW (пробитие, dmg=12)
        # p1_total=10, p2_total=24 ⇒ p2 wins (delta -14 / +14)
        rounds = [
            (_ch(Position.HIGH, Position.HIGH), _ch(Position.MID, Position.MID)),
            (_ch(Position.MID, Position.MID), _ch(Position.MID, Position.MID)),
            (_ch(Position.LOW, Position.LOW), _ch(Position.HIGH, Position.HIGH)),
        ]
        out = resolve_duel(rounds=rounds, p1_length_cm=120, p2_length_cm=50, hit_pct=10)
        # p1 пробивает в 1 и 3 раунде: 5 + 5 = 10 (10% от 50)
        assert out.p1_total_dealt == 10
        # p2 пробивает в 1 и 3 раунде: 12 + 12 = 24 (10% от 120)
        assert out.p2_total_dealt == 24
        assert out.p1_delta_cm == -14
        assert out.p2_delta_cm == 14
        assert out.winner == DuelWinner.P2


class TestZeroSumInvariant:
    """`p1_delta_cm + p2_delta_cm == 0` на любой паре раундов."""

    @pytest.mark.parametrize(
        ("p1_initial", "p2_initial", "hit_pct"),
        [
            (20, 20, 10),
            (100, 100, 10),
            (1000, 50, 25),
            (20, 1000, 5),
            (50, 50, 0),  # 0% — никогда не дилит, тоже z-sum
            (50, 50, 100),  # 100% — гигантский урон, тоже z-sum
        ],
    )
    def test_zero_sum_holds(self, p1_initial: int, p2_initial: int, hit_pct: int) -> None:
        # Произвольная пара раундов с разнообразными выборами.
        rounds = [
            (_ch(Position.HIGH, Position.MID), _ch(Position.LOW, Position.HIGH)),
            (_ch(Position.MID, Position.LOW), _ch(Position.MID, Position.MID)),
            (_ch(Position.LOW, Position.HIGH), _ch(Position.HIGH, Position.LOW)),
        ]
        out = resolve_duel(
            rounds=rounds,
            p1_length_cm=p1_initial,
            p2_length_cm=p2_initial,
            hit_pct=hit_pct,
        )
        assert out.p1_delta_cm + out.p2_delta_cm == 0


class TestPathIndependence:
    """Перестановка раундов не меняет суммарный dealt и winner-а."""

    def test_round_order_does_not_change_outcome(self) -> None:
        round_a = (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID))
        round_b = (_ch(Position.MID, Position.MID), _ch(Position.MID, Position.MID))
        round_c = (_ch(Position.LOW, Position.HIGH), _ch(Position.HIGH, Position.LOW))
        out_abc = resolve_duel(
            rounds=[round_a, round_b, round_c],
            p1_length_cm=100,
            p2_length_cm=100,
            hit_pct=10,
        )
        out_cba = resolve_duel(
            rounds=[round_c, round_b, round_a],
            p1_length_cm=100,
            p2_length_cm=100,
            hit_pct=10,
        )
        out_bac = resolve_duel(
            rounds=[round_b, round_a, round_c],
            p1_length_cm=100,
            p2_length_cm=100,
            hit_pct=10,
        )
        # Сумма dealt, дельта и winner — одинаковые независимо от порядка
        assert out_abc.p1_total_dealt == out_cba.p1_total_dealt == out_bac.p1_total_dealt
        assert out_abc.p2_total_dealt == out_cba.p2_total_dealt == out_bac.p2_total_dealt
        assert out_abc.p1_delta_cm == out_cba.p1_delta_cm == out_bac.p1_delta_cm
        assert out_abc.winner == out_cba.winner == out_bac.winner


class TestInvalidRoundCount:
    """`expected_rounds` ≠ `len(rounds)` ⇒ домен-ошибка."""

    def test_too_few_rounds(self) -> None:
        rounds = [
            (_ch(Position.HIGH, Position.HIGH), _ch(Position.HIGH, Position.HIGH)),
        ]
        with pytest.raises(InvalidRoundCountError) as exc_info:
            resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert exc_info.value.expected == 3
        assert exc_info.value.got == 1

    def test_too_many_rounds(self) -> None:
        rounds = [(_ch(Position.HIGH, Position.HIGH), _ch(Position.HIGH, Position.HIGH))] * 5
        with pytest.raises(InvalidRoundCountError) as exc_info:
            resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert exc_info.value.expected == 3
        assert exc_info.value.got == 5

    def test_empty_rounds(self) -> None:
        with pytest.raises(InvalidRoundCountError) as exc_info:
            resolve_duel(rounds=[], p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert exc_info.value.expected == 3
        assert exc_info.value.got == 0


class TestExpectedRoundsParameter:
    """`expected_rounds` ≠ DEFAULT — поддержка коротких/длинных вариантов."""

    def test_single_round_duel(self) -> None:
        # p1=HIGH/LOW, p2=LOW/MID:
        #   p1.atk=HIGH vs p2.blk=MID → пробитие, p1 дилит 10
        #   p2.atk=LOW vs p1.blk=LOW → блок, p2 дилит 0
        rounds = [
            (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID)),
        ]
        out = resolve_duel(
            rounds=rounds,
            p1_length_cm=100,
            p2_length_cm=100,
            hit_pct=10,
            expected_rounds=1,
        )
        assert out.p1_total_dealt == 10
        assert out.p2_total_dealt == 0
        assert out.winner == DuelWinner.P1
        assert len(out.rounds) == 1

    def test_five_round_duel(self) -> None:
        rounds = [
            (_ch(Position.HIGH, Position.LOW), _ch(Position.LOW, Position.MID)),
        ] * 5
        out = resolve_duel(
            rounds=rounds,
            p1_length_cm=100,
            p2_length_cm=100,
            hit_pct=10,
            expected_rounds=5,
        )
        # 5 раундов с одним и тем же исходом: p1 пробивает (10), p2 заблокирован
        assert out.p1_total_dealt == 50
        assert out.p2_total_dealt == 0
        assert out.winner == DuelWinner.P1
        assert len(out.rounds) == 5


class TestDuelOutcomeImmutability:
    """`DuelOutcome` — frozen, кортеж раундов не мутабелен."""

    def test_duel_outcome_is_frozen(self) -> None:
        rounds = [
            (_ch(Position.HIGH, Position.HIGH), _ch(Position.HIGH, Position.HIGH)),
        ] * 3
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        with pytest.raises(FrozenInstanceError):
            out.winner = DuelWinner.P1

    def test_rounds_is_tuple_not_list(self) -> None:
        rounds = [
            (_ch(Position.HIGH, Position.HIGH), _ch(Position.HIGH, Position.HIGH)),
        ] * 3
        out = resolve_duel(rounds=rounds, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert isinstance(out.rounds, tuple)
        assert len(out.rounds) == 3
