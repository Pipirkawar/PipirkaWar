"""Тесты VO `domain/pve/entities.py` (Спринт 3.1-A)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.balance.config import PveSign, Rarity, Slot
from pipirik_wars.domain.forest.entities import Item
from pipirik_wars.domain.pve.entities import (
    PveItemDrop,
    PveLocationKind,
    PveOutcomeBranch,
    PveRunOutcome,
)


def _item() -> Item:
    return Item(
        id="item.hat.test",
        slot=Slot.HAT,
        display_name="Тестовая шапка",
        rarity=Rarity.COMMON,
    )


class TestPveLocationKind:
    def test_values(self) -> None:
        assert PveLocationKind.MOUNTAINS.value == "mountains"
        assert PveLocationKind.DUNGEON.value == "dungeon"

    def test_str_inheritance(self) -> None:
        # str-enum: значение совместимо со строкой (для сериализации/JSON).
        assert isinstance(PveLocationKind.MOUNTAINS.value, str)
        assert str(PveLocationKind.MOUNTAINS.value) == "mountains"
        assert str(PveLocationKind.DUNGEON.value) == "dungeon"


class TestPveOutcomeBranch:
    def test_valid_gain(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        assert branch.name == "normal_gain"
        assert branch.sign is PveSign.GAIN
        assert branch.length_cm == 10

    def test_valid_loss(self) -> None:
        branch = PveOutcomeBranch(name="heavy_loss", sign=PveSign.LOSS, length_cm=18)
        assert branch.sign is PveSign.LOSS
        # length_cm — абсолютное значение, без знака.
        assert branch.length_cm == 18

    def test_valid_zero_length(self) -> None:
        # Граничный кейс: ветка с min=0..max=0 (баланс может занулить).
        branch = PveOutcomeBranch(name="zero", sign=PveSign.GAIN, length_cm=0)
        assert branch.length_cm == 0

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PveOutcomeBranch(name="", sign=PveSign.GAIN, length_cm=5)

    def test_negative_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="abs value"):
            PveOutcomeBranch(name="oops", sign=PveSign.LOSS, length_cm=-1)

    def test_frozen(self) -> None:
        branch = PveOutcomeBranch(name="x", sign=PveSign.GAIN, length_cm=5)
        with pytest.raises(AttributeError):
            branch.length_cm = 99


class TestPveItemDrop:
    def test_holds_item(self) -> None:
        drop = PveItemDrop(item=_item())
        assert drop.item.id == "item.hat.test"

    def test_frozen(self) -> None:
        drop = PveItemDrop(item=_item())
        with pytest.raises(AttributeError):
            drop.item = _item()


class TestPveRunOutcome:
    def test_valid_gain_with_drops(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        drop = PveItemDrop(item=_item())
        outcome = PveRunOutcome(branch=branch, length_delta_cm=10, drops=(drop,))
        assert outcome.length_delta_cm == 10
        assert len(outcome.drops) == 1

    def test_valid_loss_no_drops(self) -> None:
        branch = PveOutcomeBranch(name="heavy_loss", sign=PveSign.LOSS, length_cm=18)
        outcome = PveRunOutcome(branch=branch, length_delta_cm=-18, drops=())
        assert outcome.length_delta_cm == -18
        assert outcome.drops == ()

    def test_valid_zero_delta(self) -> None:
        # gain-ветка с length_cm=0 → delta=0.
        branch = PveOutcomeBranch(name="zero_gain", sign=PveSign.GAIN, length_cm=0)
        outcome = PveRunOutcome(branch=branch, length_delta_cm=0, drops=())
        assert outcome.length_delta_cm == 0

    def test_gain_with_negative_delta_rejected(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        with pytest.raises(ValueError, match="gain-branch"):
            PveRunOutcome(branch=branch, length_delta_cm=-10, drops=())

    def test_loss_with_positive_delta_rejected(self) -> None:
        branch = PveOutcomeBranch(name="heavy_loss", sign=PveSign.LOSS, length_cm=18)
        with pytest.raises(ValueError, match="loss-branch"):
            PveRunOutcome(branch=branch, length_delta_cm=18, drops=())

    def test_abs_delta_must_match_branch_length(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        with pytest.raises(ValueError, match="must equal branch.length_cm"):
            PveRunOutcome(branch=branch, length_delta_cm=15, drops=())

    def test_multiple_drops(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        drops = (PveItemDrop(item=_item()), PveItemDrop(item=_item()), PveItemDrop(item=_item()))
        outcome = PveRunOutcome(branch=branch, length_delta_cm=10, drops=drops)
        assert len(outcome.drops) == 3

    def test_frozen(self) -> None:
        branch = PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=10)
        outcome = PveRunOutcome(branch=branch, length_delta_cm=10, drops=())
        with pytest.raises(AttributeError):
            outcome.length_delta_cm = 99
