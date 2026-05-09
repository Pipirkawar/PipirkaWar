"""Доменный пакет «инвентарь» (ГДД §2.6, §2.8).

Спринт 3.4-A — каркас агрегата `Item` (`enchant_level: int 0..30`,
`category: ItemCategory`), domain-errors заточки (`WrongScrollCategoryError`,
`MaxLevelReachedError`, `ItemDestroyedError`) и чистого picker-а
`pick_enchant_outcome`. Без миграции и без use-case-а — это 3.4-B/C.

Связь с `domain/enchantment/` (Спринт 3.1-D): VO `Scroll(category,
blessed)` уже живёт в `pipirik_wars.domain.enchantment.entities`,
со своим `ScrollCategory(StrEnum)` и стабильными машинными
значениями `weapon_scroll`/`armor_scroll`/`jewelry_scroll` (попадают
в `audit_log.target_id`). Здесь же мы вводим **отдельный**
`ItemCategory(StrEnum)` со значениями `weapon`/`armor`/`jewelry`
(item-уровневые ярлыки, без `_scroll`-суффикса). `category-match`
проверяется по совпадению `name`-ов (`scroll.category.name ==
item.category.name`) — детали в `Item.matches_scroll(scroll)`.

Таблица соответствий (ГДД §2.8.1):

| `ItemCategory` | `Slot`-ы (см. `domain/balance/config.Slot`) | `ScrollCategory` |
|---|---|---|
| `WEAPON`  | `right_hand`, `left_hand`               | `WEAPON`  |
| `ARMOR`   | `hat`, `body`, `legs`, `boots`          | `ARMOR`   |
| `JEWELRY` | `ring`, `chain`                         | `JEWELRY` |

Скролл нельзя применить на предмет другой категории
(`WrongScrollCategoryError` — поднимается use-case-ом `EnchantItem`
в 3.4-C). Расчёт исхода ролла (`success` / `no_effect` / `drop` /
`destroy` для regular; `success_1` / `success_2` / `no_effect` /
`drop_1` / `drop_2` для blessed) — picker `pick_enchant_outcome`
здесь (3.4-A); side-эффекты (списание скролла, audit, idempotency)
— use-case `EnchantItem` (3.4-C).
"""

from pipirik_wars.domain.inventory.entities import (
    BlessedEnchantOutcome,
    EnchantOutcome,
    Item,
    ItemCategory,
    RegularEnchantOutcome,
)
from pipirik_wars.domain.inventory.errors import (
    InventoryDomainError,
    ItemDestroyedError,
    MaxLevelReachedError,
    WrongScrollCategoryError,
)
from pipirik_wars.domain.inventory.services import pick_enchant_outcome

__all__ = [
    "BlessedEnchantOutcome",
    "EnchantOutcome",
    "InventoryDomainError",
    "Item",
    "ItemCategory",
    "ItemDestroyedError",
    "MaxLevelReachedError",
    "RegularEnchantOutcome",
    "WrongScrollCategoryError",
    "pick_enchant_outcome",
]
