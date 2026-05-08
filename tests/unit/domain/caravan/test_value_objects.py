"""Тесты VO `domain/caravan/value_objects.py` (Спринт 3.2-A)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.caravan import (
    CaravanContribution,
    CaravanRole,
    CaravanStatus,
)


class TestCaravanRoleEnum:
    def test_string_values(self) -> None:
        assert CaravanRole.LEADER.value == "leader"
        assert CaravanRole.CARAVANEER.value == "caravaneer"
        assert CaravanRole.DEFENDER.value == "defender"
        assert CaravanRole.RAIDER.value == "raider"

    def test_enum_size(self) -> None:
        assert len(list(CaravanRole)) == 4

    def test_str_inheritance(self) -> None:
        assert isinstance(CaravanRole.LEADER, str)


class TestCaravanStatusEnum:
    def test_string_values(self) -> None:
        assert CaravanStatus.LOBBY.value == "lobby"
        assert CaravanStatus.IN_BATTLE.value == "in_battle"
        assert CaravanStatus.FINISHED.value == "finished"
        assert CaravanStatus.CANCELLED.value == "cancelled"

    def test_enum_size(self) -> None:
        assert len(list(CaravanStatus)) == 4


class TestCaravanContribution:
    def test_valid_positive_int(self) -> None:
        c = CaravanContribution(cm=15)
        assert c.cm == 15

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            CaravanContribution(cm=0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            CaravanContribution(cm=-5)

    def test_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            CaravanContribution(cm=10.5)  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        # bool is technically subclass of int — defensive check.
        with pytest.raises(TypeError, match="must be int"):
            CaravanContribution(cm=True)

    def test_frozen(self) -> None:
        c = CaravanContribution(cm=20)
        with pytest.raises(AttributeError):
            c.cm = 25

    def test_equality_by_value(self) -> None:
        assert CaravanContribution(cm=15) == CaravanContribution(cm=15)
        assert CaravanContribution(cm=15) != CaravanContribution(cm=20)
