"""Тесты чистого движка массового PvP (`mass_services.py`, Спринт 2.2.B).

Покрытие:

* `pair_attackers` — pairing двух кланов:
  - детерминизм по seed-у `FakeRandom`,
  - длина выхода = `max(|A|, |B|)`,
  - обе стороны переиспользуются по mod-cycle при разной длине,
  - пустые входы → `ValueError`,
  - не-положительные id → `ValueError`,
  - все элементы большей стороны представлены ровно `ceil(N/M)` раз,
  - перестановки — действительно случайные (разные seed-ы → разные выходы).
* `resolve_mass_round` — один тик:
  - 1×1 редуцируется к классическому результату,
  - симметричный 2×2 happy-path,
  - неравные стороны 3×1,
  - блок (совпадение позиций) ⇒ damage=0,
  - идентичные blocked-ходы дают draw,
  - валидация входов (несовпадение длин/выборов).
* `resolve_mass_duel` — итог:
  - zero-sum инвариант,
  - winner-determination (CLAN1/CLAN2/DRAW),
  - draw на нулевых атаках.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from pipirik_wars.domain.pvp import (
    MassDuelWinner,
    MassRoundChoice,
    Position,
    pair_attackers,
    resolve_mass_duel,
    resolve_mass_round,
)
from tests.fakes.random import FakeRandom

# ─────────────────────────── pair_attackers ───────────────────────────


class TestPairAttackers:
    """Pairing двух кланов через `IRandom.shuffle`."""

    def test_equal_size_one_to_one(self) -> None:
        rng = FakeRandom(seed=42)
        pairs = pair_attackers(attackers=[1, 2, 3], defenders=[10, 11, 12], random=rng)
        assert len(pairs) == 3
        # Все 3 атакующих использованы ровно по 1 разу.
        attackers_used = [a for a, _ in pairs]
        defenders_used = [d for _, d in pairs]
        assert sorted(attackers_used) == [1, 2, 3]
        assert sorted(defenders_used) == [10, 11, 12]

    def test_more_attackers_than_defenders_cycles_defenders(self) -> None:
        rng = FakeRandom(seed=7)
        pairs = pair_attackers(attackers=[1, 2, 3, 4, 5], defenders=[10, 11], random=rng)
        # Длина выхода = max(5, 2) = 5.
        assert len(pairs) == 5
        # Все 5 атакующих представлены по разу.
        attackers_used = [a for a, _ in pairs]
        assert sorted(attackers_used) == [1, 2, 3, 4, 5]
        # Защитники переиспользованы (только 2 уникальных).
        defenders_used = [d for _, d in pairs]
        assert set(defenders_used) <= {10, 11}
        # Каждый из 2-х защитников встречается хотя бы раз
        # (mod-cycle гарантирует покрытие при `i % 2`).
        assert set(defenders_used) == {10, 11}

    def test_more_defenders_than_attackers_cycles_attackers(self) -> None:
        rng = FakeRandom(seed=7)
        pairs = pair_attackers(attackers=[1, 2], defenders=[10, 11, 12, 13, 14], random=rng)
        assert len(pairs) == 5
        defenders_used = [d for _, d in pairs]
        assert sorted(defenders_used) == [10, 11, 12, 13, 14]
        attackers_used = [a for a, _ in pairs]
        assert set(attackers_used) == {1, 2}

    def test_singleton_each_side(self) -> None:
        rng = FakeRandom(seed=1)
        pairs = pair_attackers(attackers=[7], defenders=[42], random=rng)
        assert pairs == ((7, 42),)

    def test_attacker_appears_correct_number_of_times(self) -> None:
        rng = FakeRandom(seed=99)
        pairs = pair_attackers(
            attackers=[1, 2, 3], defenders=[10, 11, 12, 13, 14, 15, 16], random=rng
        )
        assert len(pairs) == 7
        # Каждый атакующий встречается не более ceil(7/3) = 3 раз.
        counts = Counter(a for a, _ in pairs)
        assert max(counts.values()) <= math.ceil(7 / 3)
        assert set(counts) == {1, 2, 3}

    def test_deterministic_by_seed(self) -> None:
        a = list(range(1, 8))
        d = list(range(10, 17))
        pairs_1 = pair_attackers(attackers=a, defenders=d, random=FakeRandom(seed=123))
        pairs_2 = pair_attackers(attackers=a, defenders=d, random=FakeRandom(seed=123))
        assert pairs_1 == pairs_2

    def test_different_seeds_produce_different_outputs(self) -> None:
        a = list(range(1, 8))
        d = list(range(10, 17))
        pairs_1 = pair_attackers(attackers=a, defenders=d, random=FakeRandom(seed=1))
        pairs_2 = pair_attackers(attackers=a, defenders=d, random=FakeRandom(seed=2))
        # Шанс совпадения 7! × 7! на 2 разных seed-ах астрономически мал.
        assert pairs_1 != pairs_2

    def test_empty_attackers_rejected(self) -> None:
        with pytest.raises(ValueError, match="attackers is empty"):
            pair_attackers(attackers=[], defenders=[1], random=FakeRandom())

    def test_empty_defenders_rejected(self) -> None:
        with pytest.raises(ValueError, match="defenders is empty"):
            pair_attackers(attackers=[1], defenders=[], random=FakeRandom())

    def test_non_positive_attacker_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="attacker_id must be > 0"):
            pair_attackers(attackers=[0, 1], defenders=[10], random=FakeRandom())
        with pytest.raises(ValueError, match="attacker_id must be > 0"):
            pair_attackers(attackers=[1, -2], defenders=[10], random=FakeRandom())

    def test_non_positive_defender_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="defender_id must be > 0"):
            pair_attackers(attackers=[1], defenders=[0], random=FakeRandom())
        with pytest.raises(ValueError, match="defender_id must be > 0"):
            pair_attackers(attackers=[1], defenders=[10, -3], random=FakeRandom())


# ─────────────────────────── resolve_mass_round ───────────────────────────


class TestResolveMassRound:
    """Один тик массового боя."""

    def test_1v1_reduces_to_classical_unblocked(self) -> None:
        # Bin: clan1 атакует HIGH, clan2 блокирует LOW → не блок,
        # урон = 100 * 10 / 100 = 10. Симметрично clan2 → clan1: HIGH vs LOW → 10.
        rng = FakeRandom(seed=0)
        outcome = resolve_mass_round(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
            ],
            clan1_initial_lengths={1: 100},
            clan2_initial_lengths={2: 100},
            hit_pct=10,
            random=rng,
        )
        assert outcome.clan1_total_dealt == 10
        assert outcome.clan2_total_dealt == 10
        assert len(outcome.damage_entries) == 2

    def test_1v1_full_block_zero_damage(self) -> None:
        # Оба атакуют HIGH и блокируют HIGH → blocked обе стороны.
        rng = FakeRandom(seed=0)
        outcome = resolve_mass_round(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan1_initial_lengths={1: 100},
            clan2_initial_lengths={2: 100},
            hit_pct=10,
            random=rng,
        )
        assert outcome.clan1_total_dealt == 0
        assert outcome.clan2_total_dealt == 0
        assert all(e.blocked for e in outcome.damage_entries)
        assert all(e.damage_cm == 0 for e in outcome.damage_entries)

    def test_2v2_each_attacker_resolved_once_per_direction(self) -> None:
        # 2×2: clan1→clan2 = 2 пар, clan2→clan1 = 2 пар. Всего 4 entries.
        rng = FakeRandom(seed=42)
        outcome = resolve_mass_round(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                MassRoundChoice(player_id=2, attack=Position.MID, block=Position.LOW),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=10, attack=Position.LOW, block=Position.HIGH),
                MassRoundChoice(player_id=11, attack=Position.LOW, block=Position.MID),
            ],
            clan1_initial_lengths={1: 100, 2: 100},
            clan2_initial_lengths={10: 100, 11: 100},
            hit_pct=10,
            random=rng,
        )
        assert len(outcome.damage_entries) == 4
        # Все 4 атаки идут в разные блоки → ни одна не блокирована.
        # clan1.player_1 HIGH vs clan2 block ∈ {HIGH, MID} — может быть
        # blocked если pairing назначил защитника с блоком HIGH.
        # Принципиальный инвариант: clan1_total_dealt + clan2_total_dealt
        # детерминированы по seed, их сумма ≤ 4 × 10 = 40 (4 атаки по 10 см).
        assert outcome.clan1_total_dealt + outcome.clan2_total_dealt <= 40

    def test_3v1_unequal_resolves_all_three_clan1_attacks(self) -> None:
        # 3 vs 1 — clan1→clan2: 3 пар (defender дублируется 3 раза),
        # clan2→clan1: 3 пар (attacker дублируется 3 раза).
        rng = FakeRandom(seed=11)
        outcome = resolve_mass_round(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.MID),
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.MID),
                MassRoundChoice(player_id=3, attack=Position.HIGH, block=Position.MID),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=10, attack=Position.LOW, block=Position.LOW),
            ],
            clan1_initial_lengths={1: 100, 2: 100, 3: 100},
            clan2_initial_lengths={10: 100},
            hit_pct=10,
            random=rng,
        )
        # 3 атаки clan1 → защитник 10 у которого block=LOW: HIGH vs LOW
        # пробивает → 3 удара по 10 см (path-independent: длина 10 фиксирована
        # на старте боя, не уменьшается между ударами).
        assert outcome.clan1_total_dealt == 30
        # 3 атаки clan2 (один игрок 10) → защитники 1/2/3 c block=MID:
        # LOW vs MID пробивает → 3 удара по 10 см.
        assert outcome.clan2_total_dealt == 30
        assert len(outcome.damage_entries) == 6

    def test_lengths_missing_player_rejected(self) -> None:
        with pytest.raises(ValueError, match="clan1.*lengths"):
            resolve_mass_round(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
                ],
                # пустой dict, не покрывает clan1_ids = [1]:
                clan1_initial_lengths={},
                clan2_initial_lengths={2: 100},
                hit_pct=10,
                random=FakeRandom(),
            )

    def test_lengths_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="clan2.*lengths"):
            resolve_mass_round(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
                ],
                clan1_initial_lengths={1: 100},
                # лишний player_id, которого нет в clan2_choices:
                clan2_initial_lengths={2: 100, 99: 50},
                hit_pct=10,
                random=FakeRandom(),
            )

    def test_negative_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            resolve_mass_round(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
                ],
                clan1_initial_lengths={1: -5},
                clan2_initial_lengths={2: 100},
                hit_pct=10,
                random=FakeRandom(),
            )

    @pytest.mark.parametrize("bad_pct", [-1, 101, 200])
    def test_hit_pct_out_of_range_rejected(self, bad_pct: int) -> None:
        with pytest.raises(ValueError, match="hit_pct"):
            resolve_mass_round(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
                ],
                clan1_initial_lengths={1: 100},
                clan2_initial_lengths={2: 100},
                hit_pct=bad_pct,
                random=FakeRandom(),
            )

    def test_duplicate_player_id_in_choices_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate player_id"):
            resolve_mass_round(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                    MassRoundChoice(player_id=1, attack=Position.MID, block=Position.MID),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
                ],
                clan1_initial_lengths={1: 100},
                clan2_initial_lengths={2: 100},
                hit_pct=10,
                random=FakeRandom(),
            )

    def test_deterministic_by_seed(self) -> None:
        clan1_choices = [
            MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
            MassRoundChoice(player_id=2, attack=Position.MID, block=Position.HIGH),
        ]
        clan2_choices = [
            MassRoundChoice(player_id=10, attack=Position.LOW, block=Position.MID),
            MassRoundChoice(player_id=11, attack=Position.HIGH, block=Position.LOW),
        ]
        clan1_lengths = {1: 100, 2: 100}
        clan2_lengths = {10: 100, 11: 100}
        out_a = resolve_mass_round(
            clan1_choices=clan1_choices,
            clan2_choices=clan2_choices,
            clan1_initial_lengths=clan1_lengths,
            clan2_initial_lengths=clan2_lengths,
            hit_pct=10,
            random=FakeRandom(seed=777),
        )
        out_b = resolve_mass_round(
            clan1_choices=clan1_choices,
            clan2_choices=clan2_choices,
            clan1_initial_lengths=clan1_lengths,
            clan2_initial_lengths=clan2_lengths,
            hit_pct=10,
            random=FakeRandom(seed=777),
        )
        assert out_a == out_b


# ─────────────────────────── resolve_mass_duel ───────────────────────────


class TestResolveMassDuel:
    """Итог массового боя — winner + zero-sum дельты."""

    def test_clan1_wins_when_dealt_more(self) -> None:
        # clan1 атакует HIGH в block=LOW (пробивает); clan2 атакует HIGH
        # в block=HIGH у clan1 (блок). clan1 нанёс 10, clan2 нанёс 0.
        rng = FakeRandom(seed=0)
        result = resolve_mass_duel(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.LOW),
            ],
            clan1_initial_lengths={1: 100},
            clan2_initial_lengths={2: 100},
            hit_pct=10,
            random=rng,
        )
        assert result.winner is MassDuelWinner.CLAN1
        assert result.clan1_total_dealt == 10
        assert result.clan2_total_dealt == 0
        assert result.clan1_delta_cm == 10
        assert result.clan2_delta_cm == -10

    def test_clan2_wins_when_dealt_more(self) -> None:
        rng = FakeRandom(seed=0)
        result = resolve_mass_duel(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan1_initial_lengths={1: 100},
            clan2_initial_lengths={2: 100},
            hit_pct=10,
            random=rng,
        )
        assert result.winner is MassDuelWinner.CLAN2
        assert result.clan1_total_dealt == 0
        assert result.clan2_total_dealt == 10

    def test_full_block_both_sides_is_draw(self) -> None:
        rng = FakeRandom(seed=0)
        result = resolve_mass_duel(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.HIGH),
            ],
            clan1_initial_lengths={1: 100},
            clan2_initial_lengths={2: 100},
            hit_pct=10,
            random=rng,
        )
        assert result.winner is MassDuelWinner.DRAW
        assert result.clan1_total_dealt == 0
        assert result.clan2_total_dealt == 0
        assert result.clan1_delta_cm == 0
        assert result.clan2_delta_cm == 0

    def test_zero_sum_invariant(self) -> None:
        rng = FakeRandom(seed=42)
        result = resolve_mass_duel(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW),
                MassRoundChoice(player_id=2, attack=Position.MID, block=Position.LOW),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=10, attack=Position.LOW, block=Position.HIGH),
                MassRoundChoice(player_id=11, attack=Position.LOW, block=Position.MID),
            ],
            clan1_initial_lengths={1: 100, 2: 100},
            clan2_initial_lengths={10: 100, 11: 100},
            hit_pct=10,
            random=rng,
        )
        assert result.clan1_delta_cm + result.clan2_delta_cm == 0

    def test_winner_consistent_with_dealt(self) -> None:
        # Sweep по нескольким seed-ам: всегда winner соответствует знаку дельты.
        for seed in (1, 7, 13, 21, 99, 100, 1000):
            rng = FakeRandom(seed=seed)
            result = resolve_mass_duel(
                clan1_choices=[
                    MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.MID),
                    MassRoundChoice(player_id=2, attack=Position.LOW, block=Position.HIGH),
                ],
                clan2_choices=[
                    MassRoundChoice(player_id=10, attack=Position.MID, block=Position.LOW),
                    MassRoundChoice(player_id=11, attack=Position.HIGH, block=Position.MID),
                ],
                clan1_initial_lengths={1: 100, 2: 100},
                clan2_initial_lengths={10: 100, 11: 100},
                hit_pct=10,
                random=rng,
            )
            if result.clan1_total_dealt > result.clan2_total_dealt:
                assert result.winner is MassDuelWinner.CLAN1
            elif result.clan1_total_dealt < result.clan2_total_dealt:
                assert result.winner is MassDuelWinner.CLAN2
            else:
                assert result.winner is MassDuelWinner.DRAW

    def test_path_independence_lengths_unchanged_in_round(self) -> None:
        # Path-independent: даже если в одном тике несколько ударов в одного
        # защитника, его «длина для расчёта» не уменьшается между ними.
        # 3×1 атаки в защитника длиной 100 при hit_pct=10 ⇒ 3 × 10 = 30 см
        # (НЕ 10 + 9 + 8, как было бы при «сначала уменьшим длину»).
        rng = FakeRandom(seed=11)
        result = resolve_mass_duel(
            clan1_choices=[
                MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.MID),
                MassRoundChoice(player_id=2, attack=Position.HIGH, block=Position.MID),
                MassRoundChoice(player_id=3, attack=Position.HIGH, block=Position.MID),
            ],
            clan2_choices=[
                MassRoundChoice(player_id=10, attack=Position.LOW, block=Position.LOW),
            ],
            clan1_initial_lengths={1: 100, 2: 100, 3: 100},
            clan2_initial_lengths={10: 100},
            hit_pct=10,
            random=rng,
        )
        # 3 удара по 10 см, без HP-уменьшения per-attack:
        assert result.clan1_total_dealt == 30
