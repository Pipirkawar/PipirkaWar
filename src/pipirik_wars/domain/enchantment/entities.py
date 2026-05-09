"""Domain VO «скролл заточки» (ГДД §2.8.1).

Скролл — отдельная сущность инвентаря (не предмет экипировки). У него
две оси:

- **Категория** (`ScrollCategory`) — какой класс предметов точит.
  Соответствие категория ↔ слоты экипировки (ГДД §2.8.1):

  | Категория | Слоты |
  |---|---|
  | `weapon_scroll` | `right_hand`, `left_hand` |
  | `armor_scroll`  | `hat`, `body`, `legs`, `boots` |
  | `jewelry_scroll`| `ring`, `chain` |

- **Blessed** — флаг «благословлённого» скролла (ГДД §2.8.4).
  - `False` — обычный скролл (4 исхода: `success_1` / `no_effect` /
    `drop_3` / `destroy`).
  - `True` — благословлённый (5 исходов: `success_1` / `success_2` /
    `no_effect` / `drop_1` / `drop_2`; **никогда не разрушает**
    предмет — это его ключевое отличие).

Спринт 3.1-D: VO существует, дропается из гор/данжона, **никак не
применяется** (механика заточки — Спринт 3.4). Frozen + slots для
дешёвой эквивалентности и безопасной передачи между слоями.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ScrollCategory(str, enum.Enum):
    """Категория скролла заточки (ГДД §2.8.1).

    Стабильные машинные значения — попадают в `audit_log`, в JSON
    drops, в `balance.yaml` weights. Не менять без миграции.
    """

    WEAPON = "weapon_scroll"
    ARMOR = "armor_scroll"
    JEWELRY = "jewelry_scroll"


@dataclass(frozen=True, slots=True)
class Scroll:
    """Скролл заточки (ГДД §2.8.1).

    Идентичен по категории и `blessed`-флагу: два скролла одной
    категории + одинакового флага считаются одной «единицей»
    (стак-able в инвентаре). VO не несёт `id` или владельца —
    эту мету даёт persistence-слой (3.4).

    `category` — какой класс предметов точит этот скролл.
    `blessed` — благословлённый ли скролл (см. `ScrollCategory`-doc).
    """

    category: ScrollCategory
    blessed: bool

    @property
    def scroll_id(self) -> str:
        """Стабильный машинный id для persistence-слоя (Спринт 3.4-C).

        Формат: ``{category.value}:{regular|blessed}``. Примеры:

        - `weapon_scroll:regular`
        - `weapon_scroll:blessed`
        - `armor_scroll:regular`
        - `jewelry_scroll:blessed`

        Этот id попадает в колонку `scrolls.scroll_id` (VARCHAR(64)) —
        composite-PK `(player_id, scroll_id)` гарантирует, что у
        игрока на каждую (категория, blessed)-комбинацию ровно одна
        строка с `qty INT` (стэкабельный счётчик).

        Заодно используется как `target_id` в `audit_log` для
        action-ов `ITEM_ENCHANT_ATTEMPT` / `ENCHANT_ANOMALY`
        (Спринт 3.4-C). Стабильность важна — не менять без миграции.
        """
        return f"{self.category.value}:{'blessed' if self.blessed else 'regular'}"

    @classmethod
    def from_scroll_id(cls, scroll_id: str) -> Scroll:
        """Обратная функция к `scroll_id`-property (round-trip identity).

        Pre: `scroll_id` имеет формат `{category.value}:{regular|blessed}`,
        иначе `ValueError`.

        Используется persistence-слоем (`SqlAlchemyScrollRepository`,
        Спринт 3.4-C) для восстановления `Scroll`-VO из ORM-строки.
        """
        try:
            category_value, kind = scroll_id.split(":", maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"scroll_id must be 'category:regular|blessed', got {scroll_id!r}",
            ) from exc

        if kind not in ("regular", "blessed"):
            raise ValueError(
                f"scroll_id kind must be 'regular' or 'blessed', got {kind!r} "
                f"(scroll_id={scroll_id!r})",
            )

        try:
            category = ScrollCategory(category_value)
        except ValueError as exc:
            raise ValueError(
                f"unknown scroll category {category_value!r} in scroll_id={scroll_id!r}",
            ) from exc

        return cls(category=category, blessed=(kind == "blessed"))


__all__ = ["Scroll", "ScrollCategory"]
