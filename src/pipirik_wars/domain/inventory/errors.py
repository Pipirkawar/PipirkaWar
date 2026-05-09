"""Domain-errors инвентаря и заточки (ГДД §2.8).

Все наследуют общий `InventoryDomainError` (он же — `DomainError` из
`pipirik_wars.shared.errors`), чтобы в use-case-ах 3.4-C и в bot-handler-ах
3.4-D было удобно ловить «всё, что относится к инвентарю» одним
`except InventoryDomainError`.

Эти ошибки **никогда** не пробрасываются наружу как есть: bot-handler-ы
маппят их на дружелюбные сообщения через локали `enchant-*` (см.
`current_tasks.md` секция «3.4-D — Bot UI + локали»).
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError

__all__ = [
    "InventoryDomainError",
    "ItemDestroyedError",
    "MaxLevelReachedError",
    "WrongScrollCategoryError",
]


class InventoryDomainError(DomainError):
    """База для всех ошибок инвентарного слоя.

    Не бросается напрямую — у каждого случая есть свой подкласс
    с явными атрибутами для маппинга на локали.
    """


class WrongScrollCategoryError(InventoryDomainError):
    """Скролл несовместим с категорией предмета (ГДД §2.8.1).

    Поднимается в use-case-е `EnchantItem` (3.4-C) после загрузки
    `Item` и `Scroll`: если `not item.matches_scroll(scroll)` —
    скролл не списывается, audit пишется как `ITEM_ENCHANT_ATTEMPT`
    с `outcome="wrong_category"`.

    Атрибуты:
    - `scroll_category` — категория, к которой относится попытка
      применения (`ScrollCategory`-enum).
    - `item_category` — категория предмета (`ItemCategory`-enum).
    """

    def __init__(self, *, scroll_category: object, item_category: object) -> None:
        self.scroll_category = scroll_category
        self.item_category = item_category
        super().__init__(
            f"scroll category {scroll_category!r} does not match item category {item_category!r}",
        )


class MaxLevelReachedError(InventoryDomainError):
    """Попытка перейти за границы лестницы заточки `[0, 30]` (ГДД §2.8.2).

    Бросается агрегатом `Item` в трёх случаях:
    - конструирование `Item(enchant_level=31)` (или `-1`) —
      нарушение invariant-а `__post_init__`;
    - `Item.with_enchant_level(31)` — попытка перевести в `+31`
      (логически невозможно: домен жёстко режет на `MAX_ENCHANT_LEVEL=30`).
    - `Item.with_enchant_level(-1)` — попытка `drop` в `-1`
      (clamp на `0` делается в picker-е `pick_enchant_outcome`,
      сюда уже приходит clamped-значение; если кто-то всё же
      передал `-1`, агрегат не пропустит — defence-in-depth).

    Атрибуты:
    - `item_id: str` — id предмета каталога.
    - `current_level: int` — попытка установить именно этот уровень
      (out-of-range).
    """

    def __init__(self, *, item_id: str, current_level: int) -> None:
        self.item_id = item_id
        self.current_level = current_level
        super().__init__(
            f"enchant_level {current_level} out of range [0, 30] for item {item_id!r}",
        )


class ItemDestroyedError(InventoryDomainError):
    """Попытка работать с уже уничтоженным предметом (ГДД §2.8.3).

    В Спринте 3.4-A сам агрегат `Item` ещё **не** несёт флаг
    `destroyed: bool` (см. `Item.is_destroyed()` — всегда `False`):
    «уничтоженный» предмет в use-case-е 3.4-C просто DELETE-ится
    из `inventory`, и повторный запрос по `item_id` не находит
    запись (`NotFound`). Эта ошибка зарезервирована для случая,
    когда на 3.4-C/D появится «soft-delete» с явным `destroyed`-полем
    — тогда `EnchantItem` будет проверять `if item.is_destroyed():
    raise ItemDestroyed(item_id=item.id)`.

    Атрибуты:
    - `item_id: str` — id уничтоженного предмета.
    """

    def __init__(self, *, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"item {item_id!r} was destroyed and cannot be enchanted")
