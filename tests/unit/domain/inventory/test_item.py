"""Тесты доменного агрегата `Item` (Спринт 3.4-A, A.6).

Покрытие:

* default `enchant_level=0`;
* immutability (`frozen=True`): попытка `item.enchant_level = 5` →
  `FrozenInstanceError`;
* `with_enchant_level(level)` — корректные граничные значения
  (`0`, `MAX_ENCHANT_LEVEL`); невалидные (`-1`, `MAX_ENCHANT_LEVEL + 1`)
  → `MaxLevelReachedError`;
* `is_destroyed()` — всегда `False` в Спринте 3.4-A;
* `matches_scroll(scroll)` — все 3 категории совпадают по имени enum-а
  (`weapon_scroll ↔ weapon`, `armor_scroll ↔ armor`,
  `jewelry_scroll ↔ jewelry`); попытка скрестить разные категории →
  `False`;
* `MAX_ENCHANT_LEVEL` дублирует `EnchantmentConfig.max_level`
  (в `balance.yaml`) — defence-in-depth (ГДД §2.8.2).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from pipirik_wars.domain.balance.config import Slot
from pipirik_wars.domain.enchantment import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    Item,
    ItemCategory,
    MaxLevelReachedError,
)
from pipirik_wars.domain.inventory.entities import MAX_ENCHANT_LEVEL
from tests.unit.domain.balance.factories import build_valid_balance


class TestItemConstruction:
    def test_default_enchant_level_zero(self) -> None:
        item = Item(id="item.right_hand.sword", category=ItemCategory.WEAPON)
        assert item.enchant_level == 0

    def test_explicit_enchant_level(self) -> None:
        item = Item(
            id="item.body.armor",
            category=ItemCategory.ARMOR,
            enchant_level=15,
        )
        assert item.enchant_level == 15

    @pytest.mark.parametrize("level", [0, 1, 15, 29, MAX_ENCHANT_LEVEL])
    def test_valid_boundary_levels_accepted(self, level: int) -> None:
        item = Item(id="item.ring.gold", category=ItemCategory.JEWELRY, enchant_level=level)
        assert item.enchant_level == level

    @pytest.mark.parametrize("level", [-1, -10, MAX_ENCHANT_LEVEL + 1, 100])
    def test_out_of_range_level_raises(self, level: int) -> None:
        with pytest.raises(MaxLevelReachedError) as ei:
            Item(id="item.chain.silver", category=ItemCategory.JEWELRY, enchant_level=level)
        assert ei.value.item_id == "item.chain.silver"
        assert ei.value.current_level == level

    def test_item_is_frozen(self) -> None:
        item = Item(id="item.hat.steel", category=ItemCategory.ARMOR)
        with pytest.raises(FrozenInstanceError):
            item.enchant_level = 5

    def test_equality_by_value(self) -> None:
        a = Item(id="x", category=ItemCategory.WEAPON, enchant_level=4)
        b = Item(id="x", category=ItemCategory.WEAPON, enchant_level=4)
        c = Item(id="x", category=ItemCategory.WEAPON, enchant_level=5)
        assert a == b
        assert a != c


class TestItemWithEnchantLevel:
    def test_returns_new_instance(self) -> None:
        original = Item(id="item.body.cloak", category=ItemCategory.ARMOR, enchant_level=2)
        updated = original.with_enchant_level(3)
        assert updated.enchant_level == 3
        assert original.enchant_level == 2  # immutability
        assert updated is not original
        # id и category сохраняются
        assert updated.id == original.id
        assert updated.category is original.category

    @pytest.mark.parametrize("level", [0, 1, 29, MAX_ENCHANT_LEVEL])
    def test_valid_boundary_levels(self, level: int) -> None:
        item = Item(id="item.boots.iron", category=ItemCategory.ARMOR)
        assert item.with_enchant_level(level).enchant_level == level

    @pytest.mark.parametrize("level", [-1, -100, MAX_ENCHANT_LEVEL + 1, 31, 999])
    def test_out_of_range_raises_max_level_reached(self, level: int) -> None:
        item = Item(id="item.legs.cloth", category=ItemCategory.ARMOR, enchant_level=10)
        with pytest.raises(MaxLevelReachedError) as ei:
            item.with_enchant_level(level)
        assert ei.value.item_id == "item.legs.cloth"
        assert ei.value.current_level == level

    def test_replace_compat(self) -> None:
        """`with_enchant_level` ведёт себя как `dataclasses.replace`-обёртка."""
        item = Item(id="i", category=ItemCategory.WEAPON, enchant_level=5)
        assert item.with_enchant_level(7) == replace(item, enchant_level=7)


class TestIsDestroyed:
    @pytest.mark.parametrize(
        "level",
        [0, 1, 5, 15, 29, MAX_ENCHANT_LEVEL],
    )
    def test_always_false_in_3_4_a(self, level: int) -> None:
        """Спринт 3.4-A: `Item` ещё не несёт флаг `destroyed: bool`."""
        item = Item(id="x", category=ItemCategory.WEAPON, enchant_level=level)
        assert item.is_destroyed() is False


class TestMatchesScroll:
    @pytest.mark.parametrize(
        ("item_category", "scroll_category", "expected"),
        [
            # совпадения
            (ItemCategory.WEAPON, ScrollCategory.WEAPON, True),
            (ItemCategory.ARMOR, ScrollCategory.ARMOR, True),
            (ItemCategory.JEWELRY, ScrollCategory.JEWELRY, True),
            # несовпадения (все 6 кросс-комбинаций)
            (ItemCategory.WEAPON, ScrollCategory.ARMOR, False),
            (ItemCategory.WEAPON, ScrollCategory.JEWELRY, False),
            (ItemCategory.ARMOR, ScrollCategory.WEAPON, False),
            (ItemCategory.ARMOR, ScrollCategory.JEWELRY, False),
            (ItemCategory.JEWELRY, ScrollCategory.WEAPON, False),
            (ItemCategory.JEWELRY, ScrollCategory.ARMOR, False),
        ],
    )
    @pytest.mark.parametrize("blessed", [False, True])
    def test_match_by_category_name(
        self,
        item_category: ItemCategory,
        scroll_category: ScrollCategory,
        expected: bool,
        blessed: bool,
    ) -> None:
        item = Item(id="x", category=item_category)
        scroll = Scroll(category=scroll_category, blessed=blessed)
        assert item.matches_scroll(scroll) is expected

    def test_blessed_does_not_affect_match(self) -> None:
        """`blessed` флаг — бизнес-логика roll-а, не принадлежности категории."""
        item = Item(id="x", category=ItemCategory.WEAPON)
        regular = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        blessed = Scroll(category=ScrollCategory.WEAPON, blessed=True)
        assert item.matches_scroll(regular) is True
        assert item.matches_scroll(blessed) is True


class TestItemCategoryEnum:
    def test_values_are_stable_machine_strings(self) -> None:
        """Значения попадают в audit_log.target_id — не менять без миграции."""
        assert ItemCategory.WEAPON.value == "weapon"
        assert ItemCategory.ARMOR.value == "armor"
        assert ItemCategory.JEWELRY.value == "jewelry"

    def test_names_match_scroll_category_names(self) -> None:
        """`Item.matches_scroll` строится на синхронности `name`-ов."""
        assert {c.name for c in ItemCategory} == {c.name for c in ScrollCategory}

    def test_is_str_subclass(self) -> None:
        """`(str, enum.Enum)`-mixin: `ItemCategory.X` — `str`-инстанс по value.

        Используется в `audit_log.target_id` (стабильное машинное значение)
        и в `eq` со строками из БД через `.value`.
        """
        assert isinstance(ItemCategory.WEAPON, str)
        assert ItemCategory.WEAPON.value == "weapon"


class TestItemCategoryFromSlot:
    """`ItemCategory.from_slot(Slot)` — маппинг ГДД §2.6 / §2.8.1."""

    @pytest.mark.parametrize(
        "slot",
        [Slot.RIGHT_HAND, Slot.LEFT_HAND],
    )
    def test_weapon_slots(self, slot: Slot) -> None:
        assert ItemCategory.from_slot(slot) is ItemCategory.WEAPON

    @pytest.mark.parametrize(
        "slot",
        [Slot.HAT, Slot.BODY, Slot.LEGS, Slot.BOOTS],
    )
    def test_armor_slots(self, slot: Slot) -> None:
        assert ItemCategory.from_slot(slot) is ItemCategory.ARMOR

    @pytest.mark.parametrize(
        "slot",
        [Slot.RING, Slot.CHAIN],
    )
    def test_jewelry_slots(self, slot: Slot) -> None:
        assert ItemCategory.from_slot(slot) is ItemCategory.JEWELRY

    def test_all_8_slots_have_a_mapping(self) -> None:
        """Полнота: каждый из 8 слотов — известная категория, без пробелов."""
        for slot in Slot:
            cat = ItemCategory.from_slot(slot)
            assert cat in {ItemCategory.WEAPON, ItemCategory.ARMOR, ItemCategory.JEWELRY}


class TestMaxEnchantLevelMatchesBalance:
    """`MAX_ENCHANT_LEVEL` (хардкод) дублирует `balance.yaml` (ГДД §2.8.2)."""

    def test_matches_balance_yaml(self) -> None:
        balance = build_valid_balance()
        assert balance.enchantment.max_level == MAX_ENCHANT_LEVEL
