"""Тесты domain-errors инвентаря (Спринт 3.4-A, A.6).

Покрытие:

* все 3 ошибки наследуют общий `InventoryDomainError` (он же `DomainError`);
* keyword-only конструкторы (нельзя позиционно);
* атрибуты сохраняются на инстансе (`scroll_category`, `item_category`,
  `item_id`, `current_level`);
* строковое представление (`str(exc)`) содержит ключевые поля
  (помогает в audit / debug-выхлопе).
"""

from __future__ import annotations

import pytest

from pipirik_wars.domain.enchantment import ScrollCategory
from pipirik_wars.domain.inventory import (
    InventoryDomainError,
    ItemCategory,
    ItemDestroyedError,
    MaxLevelReachedError,
    WrongScrollCategoryError,
)
from pipirik_wars.shared.errors import DomainError, PipirikError


class TestInheritanceChain:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            InventoryDomainError,
            WrongScrollCategoryError,
            MaxLevelReachedError,
            ItemDestroyedError,
        ],
    )
    def test_inherits_domain_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, DomainError)
        assert issubclass(exc_cls, PipirikError)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            WrongScrollCategoryError,
            MaxLevelReachedError,
            ItemDestroyedError,
        ],
    )
    def test_inherits_inventory_domain_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, InventoryDomainError)


class TestWrongScrollCategoryError:
    def test_keyword_only_args(self) -> None:
        with pytest.raises(TypeError):
            WrongScrollCategoryError(
                ScrollCategory.WEAPON,
                ItemCategory.ARMOR,
            )

    def test_attributes(self) -> None:
        exc = WrongScrollCategoryError(
            scroll_category=ScrollCategory.WEAPON,
            item_category=ItemCategory.ARMOR,
        )
        assert exc.scroll_category is ScrollCategory.WEAPON
        assert exc.item_category is ItemCategory.ARMOR

    def test_message_contains_categories(self) -> None:
        exc = WrongScrollCategoryError(
            scroll_category=ScrollCategory.JEWELRY,
            item_category=ItemCategory.WEAPON,
        )
        message = str(exc)
        assert "JEWELRY" in message or "jewelry" in message.lower()
        assert "WEAPON" in message or "weapon" in message.lower()

    def test_caught_by_inventory_domain_error(self) -> None:
        with pytest.raises(InventoryDomainError):
            raise WrongScrollCategoryError(
                scroll_category=ScrollCategory.WEAPON,
                item_category=ItemCategory.ARMOR,
            )


class TestMaxLevelReachedError:
    def test_keyword_only_args(self) -> None:
        with pytest.raises(TypeError):
            MaxLevelReachedError("item.x", 31)

    def test_attributes(self) -> None:
        exc = MaxLevelReachedError(item_id="item.weapon.sword", current_level=31)
        assert exc.item_id == "item.weapon.sword"
        assert exc.current_level == 31

    def test_negative_level_attribute(self) -> None:
        exc = MaxLevelReachedError(item_id="item.armor.x", current_level=-1)
        assert exc.current_level == -1

    def test_message_contains_id_and_level(self) -> None:
        exc = MaxLevelReachedError(item_id="item.weapon.x", current_level=31)
        msg = str(exc)
        assert "item.weapon.x" in msg
        assert "31" in msg

    def test_caught_by_inventory_domain_error(self) -> None:
        with pytest.raises(InventoryDomainError):
            raise MaxLevelReachedError(item_id="x", current_level=42)


class TestItemDestroyedError:
    def test_keyword_only_args(self) -> None:
        with pytest.raises(TypeError):
            ItemDestroyedError("item.x")

    def test_attribute(self) -> None:
        exc = ItemDestroyedError(item_id="item.armor.cloak")
        assert exc.item_id == "item.armor.cloak"

    def test_message_contains_id(self) -> None:
        exc = ItemDestroyedError(item_id="item.weapon.x")
        assert "item.weapon.x" in str(exc)

    def test_caught_by_inventory_domain_error(self) -> None:
        with pytest.raises(InventoryDomainError):
            raise ItemDestroyedError(item_id="x")


class TestErrorsAreDistinct:
    def test_three_distinct_subclasses(self) -> None:
        """Все 3 ошибки — разные подклассы, ловятся раздельно."""
        try:
            raise MaxLevelReachedError(item_id="x", current_level=31)
        except WrongScrollCategoryError:
            pytest.fail("MaxLevelReachedError caught as WrongScrollCategoryError")
        except MaxLevelReachedError:
            pass

        try:
            raise WrongScrollCategoryError(
                scroll_category=ScrollCategory.WEAPON,
                item_category=ItemCategory.ARMOR,
            )
        except ItemDestroyedError:
            pytest.fail("WrongScrollCategoryError caught as ItemDestroyedError")
        except WrongScrollCategoryError:
            pass
