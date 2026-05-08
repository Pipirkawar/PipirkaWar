"""Тесты VO `domain/bosses/value_objects.py` (Спринт 3.3-A)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.bosses import (
    BossDamage,
    BossFightStatus,
    BossKind,
)


class TestBossKindEnum:
    def test_string_values(self) -> None:
        assert BossKind.RAID.value == "raid"

    def test_enum_size(self) -> None:
        assert len(list(BossKind)) == 1

    def test_str_inheritance(self) -> None:
        assert isinstance(BossKind.RAID, str)


class TestBossFightStatusEnum:
    def test_string_values(self) -> None:
        assert BossFightStatus.LOBBY.value == "lobby"
        assert BossFightStatus.IN_BATTLE.value == "in_battle"
        assert BossFightStatus.FINISHED.value == "finished"
        assert BossFightStatus.CANCELLED.value == "cancelled"

    def test_enum_size(self) -> None:
        assert len(list(BossFightStatus)) == 4

    def test_str_inheritance(self) -> None:
        assert isinstance(BossFightStatus.LOBBY, str)


class TestBossDamage:
    def test_valid_positive_int(self) -> None:
        d = BossDamage(cm=5)
        assert d.cm == 5

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            BossDamage(cm=0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            BossDamage(cm=-3)

    def test_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            BossDamage(cm=4.5)  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        # bool — subclass of int; defensive check.
        with pytest.raises(TypeError, match="must be int"):
            BossDamage(cm=True)

    def test_frozen(self) -> None:
        d = BossDamage(cm=10)
        with pytest.raises(AttributeError):
            d.cm = 12

    def test_equality_by_value(self) -> None:
        assert BossDamage(cm=5) == BossDamage(cm=5)
        assert BossDamage(cm=5) != BossDamage(cm=10)
