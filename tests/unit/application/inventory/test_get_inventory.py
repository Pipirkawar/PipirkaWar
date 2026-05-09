"""Юнит-тесты `GetInventory` use-case (Спринт 3.4-D, D.1a).

Покрытие:
- Пустой инвентарь (нет items, нет scrolls) → пустой `InventoryView`;
- Инвентарь с items+scrolls → каталожные данные подтягиваются;
- `item_id` пропал из каталога → `DomainIntegrityError`;
- ScrollView корректно содержит `scroll_id`/`category`/`blessed`/`qty`.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from pipirik_wars.application.inventory import (
    GetInventory,
    InventoryView,
    ItemView,
    ScrollView,
)
from pipirik_wars.domain.balance.config import Rarity, Slot
from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    IItemRepository,
    IScrollRepository,
    Item,
    ItemCategory,
    ItemNotFoundError,
    ScrollStack,
)
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError
from tests.fakes import FakeBalanceConfig
from tests.unit.domain.balance.factories import build_valid_balance

_PLAYER_ID = 1234


class _ListBackedItemRepository(IItemRepository):
    """In-memory `IItemRepository`, поддерживающий `list_by_player`."""

    __slots__ = ("items",)

    def __init__(self, *, items: tuple[Item, ...]) -> None:
        self.items = items

    async def get(self, *, player_id: int, item_id: str) -> Item:
        for item in self.items:
            if item.id == item_id:
                return item
        raise ItemNotFoundError(player_id=player_id, item_id=item_id)

    async def add(
        self,
        *,
        player_id: int,
        item_id: str,
        now: datetime,
    ) -> Item:
        raise NotImplementedError

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        raise NotImplementedError

    async def delete(self, *, player_id: int, item_id: str) -> None:
        raise NotImplementedError

    async def list_by_player(self, *, player_id: int) -> tuple[Item, ...]:
        return self.items


class _ListBackedScrollRepository(IScrollRepository):
    """In-memory `IScrollRepository`, поддерживающий `list_by_player`."""

    __slots__ = ("stacks",)

    def __init__(self, *, stacks: tuple[ScrollStack, ...]) -> None:
        self.stacks = stacks

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        raise NotImplementedError

    async def add(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int,
        now: datetime,
    ) -> None:
        raise NotImplementedError

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        raise NotImplementedError

    async def list_by_player(self, *, player_id: int) -> tuple[ScrollStack, ...]:
        return self.stacks


class TestGetInventoryEmpty:
    @pytest.mark.asyncio
    async def test_empty_inventory_returns_empty_view(self) -> None:
        item_repo = _ListBackedItemRepository(items=())
        scroll_repo = _ListBackedScrollRepository(stacks=())
        balance = FakeBalanceConfig(build_valid_balance())
        get_inventory = GetInventory(
            item_repo=item_repo,
            scroll_repo=scroll_repo,
            balance=balance,
        )

        view = await get_inventory(player_id=_PLAYER_ID)

        assert view.items == ()
        assert view.scrolls == ()


class TestGetInventoryItemsAndScrolls:
    @pytest.mark.asyncio
    async def test_returns_item_views_with_catalog_data(self) -> None:
        item_repo = _ListBackedItemRepository(
            items=(
                Item(
                    id="item.right_hand.test_1",
                    category=ItemCategory.WEAPON,
                    enchant_level=5,
                ),
                Item(
                    id="item.body.test_1",
                    category=ItemCategory.ARMOR,
                    enchant_level=0,
                ),
            )
        )
        scroll_repo = _ListBackedScrollRepository(stacks=())
        balance = FakeBalanceConfig(build_valid_balance())
        get_inventory = GetInventory(
            item_repo=item_repo,
            scroll_repo=scroll_repo,
            balance=balance,
        )

        view = await get_inventory(player_id=_PLAYER_ID)

        assert len(view.items) == 2

        weapon = view.items[0]
        assert weapon.item_id == "item.right_hand.test_1"
        assert weapon.category is ItemCategory.WEAPON
        assert weapon.slot is Slot.RIGHT_HAND
        assert weapon.enchant_level == 5
        assert isinstance(weapon.rarity, Rarity)
        assert isinstance(weapon.display_name, str)
        assert weapon.display_name  # не пустая

        armor = view.items[1]
        assert armor.item_id == "item.body.test_1"
        assert armor.category is ItemCategory.ARMOR
        assert armor.slot is Slot.BODY
        assert armor.enchant_level == 0

    @pytest.mark.asyncio
    async def test_returns_scroll_views_with_qty(self) -> None:
        item_repo = _ListBackedItemRepository(items=())
        scroll_repo = _ListBackedScrollRepository(
            stacks=(
                ScrollStack(
                    scroll=Scroll(category=ScrollCategory.WEAPON, blessed=False),
                    qty=3,
                ),
                ScrollStack(
                    scroll=Scroll(category=ScrollCategory.ARMOR, blessed=True),
                    qty=1,
                ),
            )
        )
        balance = FakeBalanceConfig(build_valid_balance())
        get_inventory = GetInventory(
            item_repo=item_repo,
            scroll_repo=scroll_repo,
            balance=balance,
        )

        view = await get_inventory(player_id=_PLAYER_ID)

        assert len(view.scrolls) == 2

        regular_weapon = view.scrolls[0]
        assert regular_weapon.scroll_id == "weapon_scroll:regular"
        assert regular_weapon.category == "weapon_scroll"
        assert regular_weapon.blessed is False
        assert regular_weapon.qty == 3

        blessed_armor = view.scrolls[1]
        assert blessed_armor.scroll_id == "armor_scroll:blessed"
        assert blessed_armor.category == "armor_scroll"
        assert blessed_armor.blessed is True
        assert blessed_armor.qty == 1

    @pytest.mark.asyncio
    async def test_unknown_item_id_raises_integrity_error(self) -> None:
        """Если БД содержит item_id, которого нет в каталоге, → DomainIntegrityError."""
        item_repo = _ListBackedItemRepository(
            items=(
                Item(
                    id="item.nonexistent.fantasy",
                    category=ItemCategory.WEAPON,
                    enchant_level=0,
                ),
            )
        )
        scroll_repo = _ListBackedScrollRepository(stacks=())
        balance = FakeBalanceConfig(build_valid_balance())
        get_inventory = GetInventory(
            item_repo=item_repo,
            scroll_repo=scroll_repo,
            balance=balance,
        )

        with pytest.raises(DomainIntegrityError) as exc_info:
            await get_inventory(player_id=_PLAYER_ID)

        assert "item.nonexistent.fantasy" in str(exc_info.value)


class TestInventoryViewFrozen:
    def test_inventory_view_is_frozen(self) -> None:
        view = InventoryView(items=(), scrolls=())
        with pytest.raises((AttributeError, TypeError)):
            view.items = ()

    def test_item_view_is_frozen(self) -> None:
        view = ItemView(
            item_id="item.x",
            display_name="X",
            category=ItemCategory.WEAPON,
            slot=Slot.RIGHT_HAND,
            rarity=Rarity.COMMON,
            enchant_level=0,
        )
        with pytest.raises((AttributeError, TypeError)):
            view.enchant_level = 5

    def test_scroll_view_is_frozen(self) -> None:
        view = ScrollView(
            scroll_id="weapon_scroll:regular",
            category="weapon_scroll",
            blessed=False,
            qty=1,
        )
        with pytest.raises((AttributeError, TypeError)):
            view.qty = 2
