"""Тесты доменных портов `IItemRepository` (3.4-B) и `IScrollRepository` (3.4-C).

Покрытие:
* `IItemRepository` — `Protocol` с 4 методами (`get`/`add`/`update_enchant_level`/`delete`);
* `IScrollRepository` — `Protocol` с 3 методами (`get`/`add`/`consume`);
* in-memory-fake-импл проходит mypy-shape-check без специальной регистрации;
* round-trip + ошибки `ItemNotFoundError` / `ScrollNotFoundError` / `ScrollOutOfStockError`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    IItemRepository,
    IScrollRepository,
    Item,
    ItemCategory,
    ItemNotFoundError,
    ScrollNotFoundError,
    ScrollOutOfStockError,
)

NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


class _InMemoryItemRepository:
    """Простой in-memory-impl для проверки соответствия протоколу."""

    def __init__(self) -> None:
        self._rows: dict[tuple[int, str], Item] = {}

    async def get(self, *, player_id: int, item_id: str) -> Item:
        try:
            return self._rows[(player_id, item_id)]
        except KeyError:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id) from None

    async def add(self, *, player_id: int, item_id: str, now: datetime) -> Item:
        del now  # не использует — only for protocol shape parity
        item = Item(id=item_id, category=ItemCategory.WEAPON)
        self._rows[(player_id, item_id)] = item
        return item

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        if (player_id, item_id) not in self._rows:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id)
        cur = self._rows[(player_id, item_id)]
        new = cur.with_enchant_level(new_level)
        self._rows[(player_id, item_id)] = new
        return new

    async def delete(self, *, player_id: int, item_id: str) -> None:
        if (player_id, item_id) not in self._rows:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id)
        del self._rows[(player_id, item_id)]


class _InMemoryScrollRepository:
    """In-memory-fake `IScrollRepository`."""

    def __init__(self) -> None:
        self._rows: dict[tuple[int, str], int] = {}  # (player_id, scroll_id) -> qty

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        if (player_id, scroll_id) not in self._rows:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
        return Scroll.from_scroll_id(scroll_id)

    async def add(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int,
        now: datetime,
    ) -> None:
        del now  # not used in stub
        if qty <= 0:
            raise ValueError(f"qty must be > 0, got {qty}")
        self._rows[(player_id, scroll_id)] = self._rows.get((player_id, scroll_id), 0) + qty

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        available = self._rows.get((player_id, scroll_id))
        if available is None:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
        if available < qty:
            raise ScrollOutOfStockError(
                player_id=player_id,
                scroll_id=scroll_id,
                requested_qty=qty,
                available_qty=available,
            )
        self._rows[(player_id, scroll_id)] = available - qty


class TestIItemRepositoryProtocol:
    def test_in_memory_impl_conforms_to_protocol(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()  # mypy: проверяет shape
        assert hasattr(repo, "get")
        assert hasattr(repo, "add")
        assert hasattr(repo, "update_enchant_level")
        assert hasattr(repo, "delete")

    @pytest.mark.asyncio
    async def test_in_memory_impl_round_trip(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()

        added = await repo.add(player_id=1, item_id="item.right_hand.x", now=NOW)
        assert added.id == "item.right_hand.x"
        assert added.enchant_level == 0

        loaded = await repo.get(player_id=1, item_id="item.right_hand.x")
        assert loaded == added

        updated = await repo.update_enchant_level(
            player_id=1,
            item_id="item.right_hand.x",
            new_level=5,
        )
        assert updated.enchant_level == 5

    @pytest.mark.asyncio
    async def test_in_memory_impl_raises_not_found(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()
        with pytest.raises(ItemNotFoundError) as exc_info:
            await repo.get(player_id=42, item_id="item.missing")
        assert exc_info.value.player_id == 42
        assert exc_info.value.item_id == "item.missing"

    @pytest.mark.asyncio
    async def test_in_memory_impl_update_raises_not_found(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()
        with pytest.raises(ItemNotFoundError):
            await repo.update_enchant_level(
                player_id=42,
                item_id="item.missing",
                new_level=5,
            )

    @pytest.mark.asyncio
    async def test_in_memory_impl_delete_round_trip(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()
        await repo.add(player_id=1, item_id="item.right_hand.x", now=NOW)
        await repo.delete(player_id=1, item_id="item.right_hand.x")
        with pytest.raises(ItemNotFoundError):
            await repo.get(player_id=1, item_id="item.right_hand.x")

    @pytest.mark.asyncio
    async def test_in_memory_impl_delete_raises_not_found(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()
        with pytest.raises(ItemNotFoundError) as exc_info:
            await repo.delete(player_id=42, item_id="item.missing")
        assert exc_info.value.player_id == 42
        assert exc_info.value.item_id == "item.missing"


class TestIScrollRepositoryProtocol:
    def test_in_memory_impl_conforms_to_protocol(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        assert hasattr(repo, "get")
        assert hasattr(repo, "add")
        assert hasattr(repo, "consume")

    @pytest.mark.asyncio
    async def test_in_memory_add_then_get(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        await repo.add(player_id=1, scroll_id="weapon_scroll:regular", qty=3, now=NOW)
        scroll = await repo.get(player_id=1, scroll_id="weapon_scroll:regular")
        assert scroll == Scroll(category=ScrollCategory.WEAPON, blessed=False)

    @pytest.mark.asyncio
    async def test_in_memory_add_stacks_qty(self) -> None:
        repo: _InMemoryScrollRepository = _InMemoryScrollRepository()
        await repo.add(player_id=1, scroll_id="weapon_scroll:regular", qty=2, now=NOW)
        await repo.add(player_id=1, scroll_id="weapon_scroll:regular", qty=3, now=NOW)
        # consume 4 — one left
        await repo.consume(player_id=1, scroll_id="weapon_scroll:regular", qty=4)
        assert repo._rows[(1, "weapon_scroll:regular")] == 1

    @pytest.mark.asyncio
    async def test_in_memory_add_qty_zero_rejected(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        with pytest.raises(ValueError, match="qty must be > 0"):
            await repo.add(player_id=1, scroll_id="weapon_scroll:regular", qty=0, now=NOW)

    @pytest.mark.asyncio
    async def test_in_memory_get_raises_not_found(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        with pytest.raises(ScrollNotFoundError) as exc_info:
            await repo.get(player_id=42, scroll_id="weapon_scroll:regular")
        assert exc_info.value.player_id == 42
        assert exc_info.value.scroll_id == "weapon_scroll:regular"

    @pytest.mark.asyncio
    async def test_in_memory_consume_raises_not_found(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        with pytest.raises(ScrollNotFoundError):
            await repo.consume(player_id=42, scroll_id="weapon_scroll:regular")

    @pytest.mark.asyncio
    async def test_in_memory_consume_raises_out_of_stock(self) -> None:
        repo: IScrollRepository = _InMemoryScrollRepository()
        await repo.add(player_id=1, scroll_id="armor_scroll:blessed", qty=2, now=NOW)
        with pytest.raises(ScrollOutOfStockError) as exc_info:
            await repo.consume(player_id=1, scroll_id="armor_scroll:blessed", qty=5)
        assert exc_info.value.player_id == 1
        assert exc_info.value.scroll_id == "armor_scroll:blessed"
        assert exc_info.value.requested_qty == 5
        assert exc_info.value.available_qty == 2
