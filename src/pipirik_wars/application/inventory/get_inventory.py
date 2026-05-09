"""Use-case `GetInventory` (Спринт 3.4-D, D.1a).

Чтение полного инвентаря игрока для UI-команды `/inventory`:
items + scroll-stacks + display-метаданные из `IBalanceConfig`-каталога
(display_name, slot, rarity).

Зависит только от двух репозиторий-портов (`IItemRepository`,
`IScrollRepository`) и `IBalanceConfig` для каталог-lookup-а.
Не пишет в БД, не пишет audit, не лезет в idempotency. Чисто
read-only.

DTO `InventoryView`:
* `items: tuple[ItemView, ...]` — каждый `ItemView(item_id,
  display_name, category, slot, rarity, enchant_level)`.
* `scrolls: tuple[ScrollView, ...]` — каждый `ScrollView(scroll_id,
  category, blessed, qty)`.

`ItemView` обогащает доменный `Item` каталожными данными
(display_name / slot / rarity) — это нужно UI-у, чтобы отрисовать
карточку с человеческим именем «Кочерга +5», а не «item.right_hand.test_3 +5».

Если `item_id` из БД пропал из каталога между сохранением и чтением
(админ удалил из `balance.yaml`) — `_resolve_catalog_entry` бросит
`DomainIntegrityError`. UI это покажет как «предмет недоступен».
Для UI-команды `/inventory` это лучше чем тихо скрыть строку —
у игрока создаётся ложное впечатление, что предмет испарился.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.balance import IBalanceConfig
from pipirik_wars.domain.balance.config import ItemEntry, Rarity, Slot
from pipirik_wars.domain.inventory import (
    IItemRepository,
    IScrollRepository,
    ItemCategory,
)
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

__all__ = ["GetInventory", "InventoryView", "ItemView", "ScrollView"]


@dataclass(frozen=True, slots=True)
class ItemView:
    """Один предмет в инвентаре, обогащённый каталожными данными.

    Используется UI-ом `/inventory` и презентерами `+N`-display-а.
    """

    item_id: str
    display_name: str
    category: ItemCategory
    slot: Slot
    rarity: Rarity
    enchant_level: int


@dataclass(frozen=True, slots=True)
class ScrollView:
    """Один стэк скроллов в инвентаре.

    Поля параллельны `ScrollStack`, но добавляют `scroll_id` (стабильный
    машинный идентификатор для callback-data) — чтобы UI мог
    использовать `scroll_id` напрямую без пересборки из `(category,
    blessed)`-пары.
    """

    scroll_id: str
    category: str
    blessed: bool
    qty: int


@dataclass(frozen=True, slots=True)
class InventoryView:
    """Снимок инвентаря игрока на момент чтения."""

    items: tuple[ItemView, ...]
    scrolls: tuple[ScrollView, ...]


def _resolve_catalog_entry(item_id: str, *, balance: IBalanceConfig) -> ItemEntry:
    """Найти каталожную запись по `item_id` или `DomainIntegrityError`."""
    catalog = balance.get().items_catalog
    for entry in catalog:
        if entry.id == item_id:
            return entry
    raise DomainIntegrityError(f"items row references unknown item id={item_id!r}")


class GetInventory:
    """Use-case чтения инвентаря игрока для UI-команды `/inventory`."""

    __slots__ = ("_balance", "_item_repo", "_scroll_repo")

    def __init__(
        self,
        *,
        item_repo: IItemRepository,
        scroll_repo: IScrollRepository,
        balance: IBalanceConfig,
    ) -> None:
        self._item_repo = item_repo
        self._scroll_repo = scroll_repo
        self._balance = balance

    async def __call__(self, *, player_id: int) -> InventoryView:
        items_raw = await self._item_repo.list_by_player(player_id=player_id)
        scrolls_raw = await self._scroll_repo.list_by_player(player_id=player_id)

        item_views: list[ItemView] = []
        for item in items_raw:
            entry = _resolve_catalog_entry(item.id, balance=self._balance)
            item_views.append(
                ItemView(
                    item_id=item.id,
                    display_name=entry.display_name,
                    category=item.category,
                    slot=entry.slot,
                    rarity=entry.rarity,
                    enchant_level=item.enchant_level,
                )
            )

        scroll_views = tuple(
            ScrollView(
                scroll_id=stack.scroll.scroll_id,
                category=stack.scroll.category.value,
                blessed=stack.scroll.blessed,
                qty=stack.qty,
            )
            for stack in scrolls_raw
        )

        return InventoryView(items=tuple(item_views), scrolls=scroll_views)
