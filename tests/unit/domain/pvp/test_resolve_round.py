"""Тесты движка одного раунда PvP 1×1 (`resolve_round`).

Покрытие:

* **9 пар (атака × блок)** — полная матрица ГДД §7.1 (3 атаки × 3 блока),
  по 1 параметризованному кейсу на каждую пару с обеих сторон.
* **Damage formula** — целочисленное `floor(L * pct / 100)` (10% от 100 = 10,
  10% от 23 = 2, 10% от 7 = 0, 0% — никогда не наносит).
* **InvalidLengthError** — отрицательная длина ⇒ домен-ошибка.

Тесты — чистые, без БД и моков.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.pvp import (
    InvalidLengthError,
    Position,
    RoundChoice,
    resolve_round,
)


def _round(
    p1_atk: Position, p1_blk: Position, p2_atk: Position, p2_blk: Position
) -> tuple[RoundChoice, RoundChoice]:
    return RoundChoice(p1_atk, p1_blk), RoundChoice(p2_atk, p2_blk)


class TestNineAttackBlockPairsP1AttacksP2:
    """ПД 2.1.1: «юнит-тесты на все 9 пар атака×блок».

    Здесь — взгляд от лица p1 как атакующего: p1 фиксирует атаку
    `attack_pos`, p2 фиксирует блок `block_pos`. Все остальные слоты
    (`p1.block`, `p2.attack`) выбраны ТАК, чтобы не перекрывать
    встречную атаку p2 — p2.attack=LOW, p1.block=HIGH (LOW≠HIGH ⇒ p2
    пробивает p1), что фиксирует «контроль»-удар и позволяет
    проверить только p1-направление в одной таблице.
    """

    @pytest.mark.parametrize(
        ("attack_pos", "block_pos", "expected_blocked"),
        [
            # 3 совпадения по диагонали (атака блокируется одноимённым блоком)
            (Position.HIGH, Position.HIGH, True),
            (Position.MID, Position.MID, True),
            (Position.LOW, Position.LOW, True),
            # 6 несовпадений (атака пробивает не-свой блок)
            (Position.HIGH, Position.MID, False),
            (Position.HIGH, Position.LOW, False),
            (Position.MID, Position.HIGH, False),
            (Position.MID, Position.LOW, False),
            (Position.LOW, Position.HIGH, False),
            (Position.LOW, Position.MID, False),
        ],
    )
    def test_p1_attack_vs_p2_block(
        self,
        attack_pos: Position,
        block_pos: Position,
        expected_blocked: bool,
    ) -> None:
        p1, p2 = _round(
            p1_atk=attack_pos,
            p1_blk=Position.HIGH,
            p2_atk=Position.LOW,
            p2_blk=block_pos,
        )
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.p1_attack_blocked is expected_blocked
        # Проверяем damage: в блок → 0, иначе 10% от 100 = 10
        assert out.p1_damage_to_p2 == (0 if expected_blocked else 10)


class TestNineAttackBlockPairsP2AttacksP1:
    """Симметричный взгляд: p2 атакует, p1 блокирует.

    Контрольный удар, чтобы матрица была проверена с обеих сторон —
    `p1.attack=LOW`, `p2.block=HIGH` (LOW≠HIGH ⇒ p1 пробивает p2),
    отдельно от тестируемого направления.
    """

    @pytest.mark.parametrize(
        ("attack_pos", "block_pos", "expected_blocked"),
        [
            (Position.HIGH, Position.HIGH, True),
            (Position.MID, Position.MID, True),
            (Position.LOW, Position.LOW, True),
            (Position.HIGH, Position.MID, False),
            (Position.HIGH, Position.LOW, False),
            (Position.MID, Position.HIGH, False),
            (Position.MID, Position.LOW, False),
            (Position.LOW, Position.HIGH, False),
            (Position.LOW, Position.MID, False),
        ],
    )
    def test_p2_attack_vs_p1_block(
        self,
        attack_pos: Position,
        block_pos: Position,
        expected_blocked: bool,
    ) -> None:
        p1, p2 = _round(
            p1_atk=Position.LOW,
            p1_blk=block_pos,
            p2_atk=attack_pos,
            p2_blk=Position.HIGH,
        )
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.p2_attack_blocked is expected_blocked
        assert out.p2_damage_to_p1 == (0 if expected_blocked else 10)


class TestDamageFormula:
    """Damage formula = `floor(defender_length_cm * hit_pct / 100)`.

    Проверяем: целочисленное деление, погранцы (0, 100), exact-цифры.
    """

    def test_damage_full_length_at_10pct(self) -> None:
        # 100 cm * 10% = 10 (точно)
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        # p1.atk=HIGH vs p2.blk=LOW → пробивает; p2.atk=HIGH vs p1.blk=HIGH → блок
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.p1_damage_to_p2 == 10
        assert out.p2_damage_to_p1 == 0

    def test_damage_floor_division(self) -> None:
        # 23 cm * 10% = 2 (floor от 2.3, не 3 и не 2.3)
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=23, p2_length_cm=23, hit_pct=10)
        assert out.p1_damage_to_p2 == 2

    def test_damage_zero_when_length_too_small(self) -> None:
        # 7 cm * 10% = 0 (floor от 0.7) — защитник почти ничего не теряет
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=7, p2_length_cm=7, hit_pct=10)
        assert out.p1_damage_to_p2 == 0

    def test_damage_zero_at_zero_pct(self) -> None:
        # 0% урона никогда не пробивает
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=0)
        assert out.p1_damage_to_p2 == 0
        assert out.p2_damage_to_p1 == 0

    def test_damage_full_at_100pct(self) -> None:
        # 100% урона = вся длина защитника за один удар
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=50, p2_length_cm=50, hit_pct=100)
        assert out.p1_damage_to_p2 == 50

    def test_damage_zero_against_zero_length_defender(self) -> None:
        # Защитник с 0 см теряет 0 даже при пробитии (нечего терять)
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=0, hit_pct=10)
        assert out.p1_attack_blocked is False
        assert out.p1_damage_to_p2 == 0


class TestRoundOutcomeShape:
    """`RoundOutcome` сохраняет выборы и флаги обеих сторон корректно."""

    def test_outcome_preserves_choices(self) -> None:
        p1 = RoundChoice(Position.HIGH, Position.MID)
        p2 = RoundChoice(Position.LOW, Position.HIGH)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.p1_choice == p1
        assert out.p2_choice == p2

    def test_outcome_both_blocked(self) -> None:
        # Оба выбрали HIGH-атаку и оба блокируют HIGH ⇒ обе атаки блокированы
        p1 = RoundChoice(Position.HIGH, Position.HIGH)
        p2 = RoundChoice(Position.HIGH, Position.HIGH)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        assert out.p1_attack_blocked is True
        assert out.p2_attack_blocked is True
        assert out.p1_damage_to_p2 == 0
        assert out.p2_damage_to_p1 == 0

    def test_outcome_both_hit(self) -> None:
        # Оба пробивают одновременно (HIGH-атака против LOW-блока с обеих сторон)
        p1 = RoundChoice(Position.HIGH, Position.LOW)
        p2 = RoundChoice(Position.HIGH, Position.LOW)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=80, hit_pct=10)
        assert out.p1_attack_blocked is False
        assert out.p2_attack_blocked is False
        assert out.p1_damage_to_p2 == 8  # 10% от 80
        assert out.p2_damage_to_p1 == 10  # 10% от 100


class TestInvalidLengthError:
    """Защита от отрицательных длин в чистом резолвере."""

    def test_p1_length_negative(self) -> None:
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.HIGH)
        with pytest.raises(InvalidLengthError) as exc_info:
            resolve_round(p1=p1, p2=p2, p1_length_cm=-1, p2_length_cm=100, hit_pct=10)
        assert exc_info.value.side == "p1"
        assert exc_info.value.length_cm == -1

    def test_p2_length_negative(self) -> None:
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.HIGH)
        with pytest.raises(InvalidLengthError) as exc_info:
            resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=-5, hit_pct=10)
        assert exc_info.value.side == "p2"
        assert exc_info.value.length_cm == -5

    def test_zero_length_is_valid(self) -> None:
        # 0 см — валидно (теоретический эджкейс, use-case фильтрует по
        # min_length_cm=20 на входе в бой)
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.HIGH)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=0, p2_length_cm=0, hit_pct=10)
        assert out.p1_damage_to_p2 == 0
        assert out.p2_damage_to_p1 == 0


class TestImmutability:
    """Frozen value-objects: попытка мутации ⇒ `dataclasses.FrozenInstanceError`."""

    def test_round_choice_is_frozen(self) -> None:
        choice = RoundChoice(Position.HIGH, Position.LOW)
        with pytest.raises(FrozenInstanceError):
            choice.attack = Position.MID

    def test_round_outcome_is_frozen(self) -> None:
        p1, p2 = _round(Position.HIGH, Position.HIGH, Position.HIGH, Position.HIGH)
        out = resolve_round(p1=p1, p2=p2, p1_length_cm=100, p2_length_cm=100, hit_pct=10)
        with pytest.raises(FrozenInstanceError):
            out.p1_damage_to_p2 = 999
