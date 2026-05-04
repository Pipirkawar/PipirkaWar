"""Тесты структуры domain-сущностей леса.

Сущности — `frozen=True, slots=True` dataclass-ы, поэтому минимальный
обязательный контракт здесь — иммутабельность и единичная идентичность
ADT-конструкторов `Drop`. Бизнес-логику расчёта проверяет
`test_services.py`.
"""

from __future__ import annotations

import pytest

from pipirik_wars.domain.forest.entities import (
    ForestRunOutcome,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    OutcomeBranch,
    Rarity,
    Slot,
)


def _item() -> Item:
    return Item(
        id="item.hat.x",
        slot=Slot.HAT,
        display_name="Тест",
        rarity=Rarity.COMMON,
    )


class TestImmutability:
    def test_item_frozen(self) -> None:
        item = _item()
        with pytest.raises(AttributeError):
            item.id = "other"

    def test_outcome_frozen(self) -> None:
        outcome = ForestRunOutcome(
            branch=OutcomeBranch(name="scarce", length_cm=3),
            length_cm=3,
            drop=NoDrop(),
        )
        with pytest.raises(AttributeError):
            outcome.length_cm = 99


class TestDropADT:
    def test_no_drop_singleton_value(self) -> None:
        # `NoDrop` — пустой dataclass; два экземпляра равны по значению.
        assert NoDrop() == NoDrop()

    def test_item_drop_carries_item(self) -> None:
        item = _item()
        drop = ItemDrop(item=item)
        assert drop.item is item

    def test_name_drop_carries_name(self) -> None:
        drop = NameDrop(name=Name(value="Колян"))
        assert drop.name.value == "Колян"

    def test_pattern_match_no_drop(self) -> None:
        drop = NoDrop()
        match drop:
            case NoDrop():
                tag = "no"
            case ItemDrop():
                tag = "item"
            case NameDrop():
                tag = "name"
        assert tag == "no"

    def test_pattern_match_item_drop(self) -> None:
        drop = ItemDrop(item=_item())
        match drop:
            case NoDrop():
                tag = "no"
            case ItemDrop(item=i):
                tag = i.slot.value
            case NameDrop():
                tag = "name"
        assert tag == "hat"

    def test_pattern_match_name_drop(self) -> None:
        drop = NameDrop(name=Name(value="Колян"))
        match drop:
            case NoDrop():
                tag = "no"
            case ItemDrop():
                tag = "item"
            case NameDrop(name=n):
                tag = n.value
        assert tag == "Колян"
