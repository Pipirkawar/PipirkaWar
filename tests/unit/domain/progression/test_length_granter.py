"""Unit-тесты `domain.progression.LengthGrantResult` (Спринт 1.6.D).

Проверяем инварианты frozen-dataclass-а: новая длина >= 0, clamped_from
не может быть меньше applied_delta_cm.
"""

from __future__ import annotations

import pytest

from pipirik_wars.domain.progression import LengthGrantResult


class TestLengthGrantResult:
    def test_valid_no_clamp(self) -> None:
        result = LengthGrantResult(
            applied_delta_cm=100,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=200,
        )
        assert result.applied_delta_cm == 100
        assert result.clamped_from is None

    def test_valid_with_clamp(self) -> None:
        result = LengthGrantResult(
            applied_delta_cm=50,
            clamped_from=200,
            triggered_soft_ban=False,
            new_length_cm=150,
        )
        assert result.clamped_from == 200

    def test_negative_new_length_raises(self) -> None:
        with pytest.raises(ValueError, match="new_length_cm must be >= 0"):
            LengthGrantResult(
                applied_delta_cm=-10,
                clamped_from=None,
                triggered_soft_ban=False,
                new_length_cm=-1,
            )

    def test_clamped_from_less_than_applied_raises(self) -> None:
        with pytest.raises(ValueError, match="clamped_from"):
            LengthGrantResult(
                applied_delta_cm=100,
                clamped_from=50,
                triggered_soft_ban=False,
                new_length_cm=200,
            )

    def test_zero_applied_with_clamped_from(self) -> None:
        # Полностью исчерпанный лимит: applied=0, clamped_from=исходная дельта.
        result = LengthGrantResult(
            applied_delta_cm=0,
            clamped_from=500,
            triggered_soft_ban=False,
            new_length_cm=100,
        )
        assert result.applied_delta_cm == 0
        assert result.clamped_from == 500

    def test_negative_applied_for_refund(self) -> None:
        # admin_refund: applied=-100, clamped_from=None.
        result = LengthGrantResult(
            applied_delta_cm=-100,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=400,
        )
        assert result.applied_delta_cm == -100
