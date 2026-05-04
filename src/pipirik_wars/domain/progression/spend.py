"""Правило 20 см (ГДД §3.1).

«После списания у игрока должно остаться **≥ `MIN_LENGTH_AFTER_SPEND_CM`** см».

Применяется ко всем активностям, где есть риск потери длины:

- ⛰️ горы (`SpendAction.MOUNTAINS`),
- 🏰 данжон (`SpendAction.DUNGEON`),
- ⚔️ PvP 1×1 (`SpendAction.PVP_1V1`),
- ⚔️ масс-PvP (`SpendAction.PVP_MASS`),
- 🐪 караван — взнос караванщика (`SpendAction.CARAVAN_MERCHANT`),
  защита (`SpendAction.CARAVAN_DEFENDER`), рейд (`SpendAction.CARAVAN_RAIDER`),
- 🐉 рейд-босс (`SpendAction.RAID_BOSS`),
- 📐 прокачка толщины (`SpendAction.THICKNESS_UPGRADE`).

**Не** применяется к активностям, которые **только дают** длину
(🌲 лес, 🔮 предсказание) — там `cost_cm == 0` и use-case просто
не зовёт `require_spend(...)`. Соответственно «лес всегда ок» — это
не специальный кейс в `can_spend(...)`, а отсутствие вызова.
"""

from __future__ import annotations

import enum
from typing import Final

from pipirik_wars.domain.progression.errors import InsufficientLengthError

MIN_LENGTH_AFTER_SPEND_CM: Final[int] = 20
"""Нижний порог длины (ГДД §3.1)."""


class SpendAction(str, enum.Enum):
    """Список активностей, которые подпадают под правило 20 см.

    Используется в сообщениях ошибок (`InsufficientLengthError.action`)
    и в audit-записях (`audit_log.target_kind`/`reason`). Не привязан
    к конкретному use-case — каждый use-case передаёт свой член enum
    при вызове `require_spend(action=...)`.
    """

    MOUNTAINS = "mountains"
    DUNGEON = "dungeon"
    PVP_1V1 = "pvp_1v1"
    PVP_MASS = "pvp_mass"
    CARAVAN_MERCHANT = "caravan_merchant"
    CARAVAN_DEFENDER = "caravan_defender"
    CARAVAN_RAIDER = "caravan_raider"
    RAID_BOSS = "raid_boss"
    THICKNESS_UPGRADE = "thickness_upgrade"


def can_spend(*, length_cm: int, cost_cm: int) -> bool:
    """Проверка инварианта «20 см» (ГДД §3.1).

    Возвращает `True`, если игрок с длиной `length_cm` может потратить
    `cost_cm` см и при этом сохранить как минимум
    `MIN_LENGTH_AFTER_SPEND_CM` см. Не имеет side-эффектов.

    Параметры:
    - `length_cm` — текущая длина игрока, ≥ 0.
    - `cost_cm` — стоимость операции, ≥ 0. Для бесплатных активностей
      (лес, предсказание) функцию не зовут вовсе.

    Бросает `ValueError` для некорректных аргументов (отрицательные значения).
    """
    if length_cm < 0:
        raise ValueError(f"length_cm must be >= 0, got {length_cm}")
    if cost_cm < 0:
        raise ValueError(f"cost_cm must be >= 0, got {cost_cm}")
    return length_cm - cost_cm >= MIN_LENGTH_AFTER_SPEND_CM


def require_spend(
    *,
    length_cm: int,
    cost_cm: int,
    action: SpendAction,
) -> None:
    """Императивная версия `can_spend(...)`: бросает `InsufficientLengthError`.

    Использование внутри use-case-а:

    >>> from pipirik_wars.domain.progression import SpendAction, require_spend
    >>> require_spend(length_cm=50, cost_cm=30, action=SpendAction.THICKNESS_UPGRADE)
    Traceback (most recent call last):
        ...
    pipirik_wars.domain.progression.errors.InsufficientLengthError: ...
    """
    if not can_spend(length_cm=length_cm, cost_cm=cost_cm):
        raise InsufficientLengthError(
            length_cm=length_cm,
            cost_cm=cost_cm,
            min_after_spend_cm=MIN_LENGTH_AFTER_SPEND_CM,
            action=action.value,
        )
