"""Domain-агрегат `Item` (инвентарный предмет с заточкой) + `ItemCategory`.

`Item` — отдельный агрегат от каталожного `Item` в
`domain/forest/entities.Item` (тот — VO дропа `(id, slot, display_name,
rarity)`, без enchant-state). Здесь — owned-предмет игрока с
изменяющимся `enchant_level: int 0..30` (ГДД §2.8.2). Категория
(`weapon` / `armor` / `jewelry`) выводится из слота согласно
ГДД §2.8.1.

`ItemCategory` намеренно **не пересекается** по значениям с
`pipirik_wars.domain.enchantment.entities.ScrollCategory` (там
`weapon_scroll`/`armor_scroll`/`jewelry_scroll`): это разные
бизнес-сущности, попадающие в `audit_log.target_id` под разными
ярлыками. `category-match` проверяется через `Item.matches_scroll(scroll)`
сравнением имён `name` (а не `value`) — `WEAPON ↔ WEAPON`, и т. д.

Спринт 3.4-A — только агрегат + методы валидации (`with_enchant_level`,
`is_destroyed`, `matches_scroll`). Persistence (миграция Alembic
`add_enchant_level_to_items` + ORM-маппинг + `IItemRepository.
update_enchant_level(...)`) — Спринт 3.4-B. Use-case `EnchantItem`
(load → category-check → roll → audit) — Спринт 3.4-C.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace

from pipirik_wars.domain.balance.config import Slot
from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.inventory.errors import (
    MaxLevelReachedError,
)

__all__ = [
    "MAX_ENCHANT_LEVEL",
    "BlessedEnchantOutcome",
    "EnchantOutcome",
    "Item",
    "ItemCategory",
    "RegularEnchantOutcome",
]


# Жёсткий потолок лестницы заточки (ГДД §2.8.2). Хардкодится
# в домене (defence-in-depth), даже если в `balance.yaml` `max_level`
# указан с опечаткой/выше — pydantic-инвариант в `EnchantmentConfig`
# проверит совпадение и упадёт на старте.
MAX_ENCHANT_LEVEL: int = 30


class ItemCategory(str, enum.Enum):
    """Категория предмета экипировки для целей заточки (ГДД §2.8.1).

    Стабильные машинные значения — попадают в `audit_log.target_id`
    при `ITEM_ENCHANT_ATTEMPT` (Спринт 3.4-C). Не менять без миграции.

    Соответствие категория ↔ слоты экипировки (ГДД §2.6, §2.8.1):

    | Категория | Слоты |
    |---|---|
    | `WEAPON`  | `right_hand`, `left_hand` |
    | `ARMOR`   | `hat`, `body`, `legs`, `boots` |
    | `JEWELRY` | `ring`, `chain` |

    Категория **не** хранится в `items_catalog` — она выводится из
    `Slot` (см. `ItemCategory.from_slot`). Это сделано, чтобы каталог
    оставался плоским и одна правка слота автоматически меняла
    категорию.
    """

    WEAPON = "weapon"
    ARMOR = "armor"
    JEWELRY = "jewelry"

    @classmethod
    def from_slot(cls, slot: Slot) -> ItemCategory:
        """Маппинг слота экипировки → категории заточки (ГДД §2.6, §2.8.1).

        | Слоты | Категория |
        |---|---|
        | `right_hand`, `left_hand`           | `WEAPON`  |
        | `hat`, `body`, `legs`, `boots`      | `ARMOR`   |
        | `ring`, `chain`                     | `JEWELRY` |

        Используется репозиторием `IItemRepository` (Спринт 3.4-B) для
        восстановления `Item.category` из строки таблицы `items` —
        категория **не** хранится в БД, она выводится из `Slot`
        (один источник правды — каталог `items_catalog` в `balance.yaml`).

        Если в будущем добавят 9-й слот, не покрытый таблицей выше, —
        упадёт `ValueError` (явная защита, чтобы не пропустить
        миграционный пробел).
        """
        if slot in (Slot.RIGHT_HAND, Slot.LEFT_HAND):
            return cls.WEAPON
        if slot in (Slot.HAT, Slot.BODY, Slot.LEGS, Slot.BOOTS):
            return cls.ARMOR
        if slot in (Slot.RING, Slot.CHAIN):
            return cls.JEWELRY
        raise ValueError(f"slot {slot!r} has no enchant category mapping")


class RegularEnchantOutcome(str, enum.Enum):
    """4 исхода обычной заточки (ГДД §2.8.3).

    - `SUCCESS` — `+1` к `enchant_level`. В safe-zone (`level <
      safe_zone_max_level`) — единственный возможный исход.
    - `NO_EFFECT` — без изменений (`enchant_level` не меняется,
      скролл всё равно списывается).
    - `DROP` — `-1` к `enchant_level` (с clamp на 0: предмет на
      `+0` остаётся на `+0`).
    - `DESTROY` — предмет уничтожен; в use-case-е 3.4-C это
      приведёт к удалению из `inventory` + audit-нотификации.
    """

    SUCCESS = "success"
    NO_EFFECT = "no_effect"
    DROP = "drop"
    DESTROY = "destroy"


class BlessedEnchantOutcome(str, enum.Enum):
    """5 исходов благословлённой заточки (ГДД §2.8.4).

    Главное отличие от `RegularEnchantOutcome` — **никогда не
    разрушает** предмет (`DESTROY` отсутствует). Платится это
    дополнительным «расщеплением» успехов на `+1` (`SUCCESS_1`)
    и `+2` (`SUCCESS_2`), а падение — на `-1` (`DROP_1`) и
    `-2` (`DROP_2`).

    Жёсткое правило `+29` (ГДД §2.8.4): на `level == 29` исход
    `SUCCESS_2` запрещён (он повёл бы предмет за `MAX_ENCHANT_LEVEL`).
    Pydantic-инвариант `EnchantmentConfig` проверяет
    `blessed_outcomes_per_level["29"].success_2 == 0.0`.
    """

    SUCCESS_1 = "success_1"
    SUCCESS_2 = "success_2"
    NO_EFFECT = "no_effect"
    DROP_1 = "drop_1"
    DROP_2 = "drop_2"


EnchantOutcome = RegularEnchantOutcome | BlessedEnchantOutcome


@dataclass(frozen=True, slots=True)
class Item:
    """Owned-предмет игрока с заточкой (ГДД §2.6, §2.8).

    Спринт 3.4-A — VO-агрегат без persistence: `id` / `category`
    хранятся для домен-проверок (`matches_scroll`), `enchant_level`
    меняется чистыми методами (`with_enchant_level`).

    `id` — стабильный машинный идентификатор каталога (`item.<slot>.<short>`,
    см. `domain/balance/config.py::ItemEntry.id`); один и тот же `id`
    может принадлежать многим игрокам — owner-id будет сидеть в БД
    в Спринте 3.4-B (поле `inventory.player_id`). Здесь его нет —
    use-case `EnchantItem` загружает Item по `(player_id, item_id)`
    из `IItemRepository`.

    `enchant_level: int 0..30` (ГДД §2.8.2) — текущий уровень заточки.
    `0` для свежедропнутых предметов (Спринт 3.4-B миграция выставит
    `default=0` для legacy-предметов).
    """

    id: str
    category: ItemCategory
    enchant_level: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.enchant_level <= MAX_ENCHANT_LEVEL:
            raise MaxLevelReachedError(
                item_id=self.id,
                current_level=self.enchant_level,
            )

    def with_enchant_level(self, level: int) -> Item:
        """Вернуть копию `Item` с заданным уровнем заточки.

        Валидация:
        - `level < 0` → `MaxLevelReachedError` (логически уровень не может
          быть отрицательным; clamp на `0` делается в picker-е, см.
          `pick_enchant_outcome` ниже — а сюда приходит уже clamped
          значение).
        - `level > MAX_ENCHANT_LEVEL` → `MaxLevelReachedError` (даже для
          blessed на `+29 → success_1 = +30` это валидно, но
          `+29 → success_2 = +31` — нет; pydantic-инвариант
          `blessed_outcomes_per_level["29"].success_2 == 0.0`
          гарантирует, что picker никогда не вернёт `SUCCESS_2`
          на `+29`, defence-in-depth).
        """
        if not 0 <= level <= MAX_ENCHANT_LEVEL:
            raise MaxLevelReachedError(item_id=self.id, current_level=level)
        return replace(self, enchant_level=level)

    def is_destroyed(self) -> bool:
        """Уничтожен ли предмет.

        В Спринте 3.4-A `Item` не несёт поля `destroyed: bool` —
        «уничтоженный» предмет в use-case-е 3.4-C просто удаляется
        из `inventory` (DELETE row), а не помечается флагом. Метод
        возвращает `False` для **существующего** in-memory `Item`-а
        (если он у тебя есть, он не уничтожен — иначе use-case
        бросил бы `ItemDestroyedError`). Метод выделен **отдельно**
        ради ясности контракта: 3.4-C / 3.4-D могут расширить
        агрегат полем `destroyed: bool` без слома сигнатур.
        """
        return False

    def matches_scroll(self, scroll: Scroll) -> bool:
        """Проверка совместимости скролла и предмета по категории.

        Скролл `Scroll(category=ScrollCategory.WEAPON, blessed=...)`
        совместим с `Item(category=ItemCategory.WEAPON, ...)` —
        сравнение по `Enum.name` (а не `Enum.value`, так как у этих
        двух enum-ов значения разные: `weapon_scroll` vs `weapon`).

        Use-case `EnchantItem` (3.4-C) использует это в гарде:

            if not item.matches_scroll(scroll):
                raise WrongScrollCategoryError(
                    scroll_category=scroll.category,
                    item_category=item.category,
                )
        """
        return _scroll_to_item_category(scroll.category) is self.category


def _scroll_to_item_category(scroll_category: ScrollCategory) -> ItemCategory:
    """Маппинг `ScrollCategory → ItemCategory` через имя enum-а.

    Имена обоих enum-ов синхронизированы (`WEAPON`/`ARMOR`/`JEWELRY`),
    поэтому `ItemCategory[scroll_category.name]` детерминирован.
    Если в будущем добавят новую категорию в один enum, но забудут
    в другой — `KeyError` на старте теста вместо тихого расхождения.
    """
    return ItemCategory[scroll_category.name]
