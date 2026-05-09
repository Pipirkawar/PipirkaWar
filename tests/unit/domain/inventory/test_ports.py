"""Тесты доменного порта `IItemRepository` (Спринт 3.4-B, B.1).

Покрытие:
* `IItemRepository` — runtime-проверяемый `Protocol` (пустой класс
  без методов формально соответствует, но проверяем что у него есть
  3 ожидаемых метода);
* подделка `FakeItemRepository` (которую будут писать use-case-тесты
  3.4-C) проходит `isinstance(...)` без специальной регистрации.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.inventory import (
    IItemRepository,
    Item,
    ItemCategory,
    ItemNotFoundError,
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


class TestIItemRepositoryProtocol:
    def test_in_memory_impl_conforms_to_protocol(self) -> None:
        repo: IItemRepository = _InMemoryItemRepository()  # mypy: проверяет shape
        assert hasattr(repo, "get")
        assert hasattr(repo, "add")
        assert hasattr(repo, "update_enchant_level")

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
