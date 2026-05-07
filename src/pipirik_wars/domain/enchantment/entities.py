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


__all__ = ["Scroll", "ScrollCategory"]
