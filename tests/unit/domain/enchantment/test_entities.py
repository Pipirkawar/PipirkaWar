"""Тесты VO `Scroll` и `ScrollCategory` (Спринт 3.1-D).

В 3.1-D scroll — лишь VO (категория + blessed-флаг); use-механика
применения скролла к предмету (`EnchantItem`-use-case + лестница
уровней + ±исходы) — Спринт 3.4. Тесты здесь проверяют только
свойства VO: эквивалентность, неизменяемость, стабильность
машинных значений категорий (последнее важно для `audit_log`-а
и JSON-сериализации в `drops`).
"""

from __future__ import annotations

import dataclasses

import pytest

from pipirik_wars.domain.enchantment import Scroll, ScrollCategory


class TestScrollCategoryValues:
    """Стабильность машинных значений `ScrollCategory`.

    Эти строки попадают в `audit_log.target_id`, в JSON drops в
    `mountain_runs.drops`/`dungeon_runs.drops`, в веса в
    `balance.yaml`. Сменить можно только с миграцией.
    """

    def test_weapon_value_is_weapon_scroll(self) -> None:
        assert ScrollCategory.WEAPON.value == "weapon_scroll"

    def test_armor_value_is_armor_scroll(self) -> None:
        assert ScrollCategory.ARMOR.value == "armor_scroll"

    def test_jewelry_value_is_jewelry_scroll(self) -> None:
        assert ScrollCategory.JEWELRY.value == "jewelry_scroll"

    def test_categories_are_string_enum(self) -> None:
        assert ScrollCategory("weapon_scroll") is ScrollCategory.WEAPON
        assert ScrollCategory("armor_scroll") is ScrollCategory.ARMOR
        assert ScrollCategory("jewelry_scroll") is ScrollCategory.JEWELRY

    def test_three_categories_total(self) -> None:
        assert {c.value for c in ScrollCategory} == {
            "weapon_scroll",
            "armor_scroll",
            "jewelry_scroll",
        }


class TestScrollVO:
    """Свойства VO `Scroll`."""

    def test_scroll_is_frozen(self) -> None:
        scroll = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            scroll.category = ScrollCategory.ARMOR

    def test_two_equal_scrolls_compare_equal(self) -> None:
        a = Scroll(category=ScrollCategory.WEAPON, blessed=True)
        b = Scroll(category=ScrollCategory.WEAPON, blessed=True)
        assert a == b
        assert hash(a) == hash(b)

    def test_blessed_flag_distinguishes(self) -> None:
        regular = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        blessed = Scroll(category=ScrollCategory.WEAPON, blessed=True)
        assert regular != blessed

    def test_category_distinguishes(self) -> None:
        weapon = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        armor = Scroll(category=ScrollCategory.ARMOR, blessed=False)
        assert weapon != armor

    def test_supports_set_membership(self) -> None:
        # Скроллы стак-абильны в инвентаре (3.4) — VO должен корректно
        # работать в `set` / `dict.keys`.
        a = Scroll(category=ScrollCategory.JEWELRY, blessed=False)
        b = Scroll(category=ScrollCategory.JEWELRY, blessed=False)
        c = Scroll(category=ScrollCategory.JEWELRY, blessed=True)
        bag = {a, b, c}
        assert len(bag) == 2  # a и b сливаются


__all__: tuple[str, ...] = ()
