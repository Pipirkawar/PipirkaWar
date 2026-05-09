"""Тесты VO `RouletteOutcome` (Спринт 3.5-A).

Покрывают invariant-проверки `__post_init__` и неизменяемость VO.
Сам machine-id-enum `RouletteOutcomeKind` не тестируется отдельно —
он тривиальный StrEnum, его значения проверяются интеграционным
тестом `tests/integration/test_balance_yaml.py` (через парсинг
`config/balance.yaml::roulette.free.outcomes`).
"""

from __future__ import annotations

import dataclasses

import pytest

from pipirik_wars.domain.roulette import RouletteOutcome
from pipirik_wars.domain.roulette.entities import RouletteOutcomeKind


class TestRouletteOutcomePostInit:
    """`__post_init__` сторожит invariant `kind ↔ length_cm`."""

    def test_length_kind_with_length_cm_ok(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        assert outcome.kind is RouletteOutcomeKind.LENGTH
        assert outcome.length_cm == 42

    def test_length_kind_without_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="requires length_cm"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH)

    def test_length_kind_with_zero_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=0)

    def test_length_kind_with_negative_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=-5)

    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
            RouletteOutcomeKind.CRYPTO_LOT,
        ],
    )
    def test_non_length_kind_without_length_cm_ok(
        self,
        kind: RouletteOutcomeKind,
    ) -> None:
        outcome = RouletteOutcome(kind=kind)
        assert outcome.kind is kind
        assert outcome.length_cm is None

    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
            RouletteOutcomeKind.CRYPTO_LOT,
        ],
    )
    def test_non_length_kind_with_length_cm_raises(
        self,
        kind: RouletteOutcomeKind,
    ) -> None:
        with pytest.raises(ValueError, match="must have length_cm=None"):
            RouletteOutcome(kind=kind, length_cm=10)


class TestRouletteOutcomeImmutability:
    """frozen-VO нельзя мутировать."""

    def test_outcome_is_frozen(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.ITEM)
        with pytest.raises(dataclasses.FrozenInstanceError):
            outcome.length_cm = 5

    def test_outcomes_with_same_fields_compare_equal(self) -> None:
        a = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        b = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        assert a == b
        assert hash(a) == hash(b)

    def test_outcomes_with_different_fields_compare_unequal(self) -> None:
        a = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        b = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=43)
        assert a != b
