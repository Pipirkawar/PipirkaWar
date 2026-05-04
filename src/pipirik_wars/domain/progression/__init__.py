"""Доменная подсистема «прогрессия» (ГДД §3, §4).

Сейчас отвечает за **правило 20 см** (ГДД §3.1) — нижний порог длины,
ниже которого игрок не может участвовать в активностях с риском
потери длины. Подсистема намеренно крошечная и чистая: тут нет ни
БД, ни порта на repo — это **бизнес-правило**, которое use-case-ы
вызывают перед списанием.

Расширение в следующих спринтах:

- 1.4: таблица стоимости толщины + use-case `UpgradeThickness`,
  использующий `require_spend(...)` перед списанием.
- 3.1: горы / данжон / караван-merchant — каждый зовёт
  `require_spend(...)` со своим `cost_cm`.
"""

from pipirik_wars.domain.progression.errors import InsufficientLengthError
from pipirik_wars.domain.progression.spend import (
    MIN_LENGTH_AFTER_SPEND_CM,
    SpendAction,
    can_spend,
    require_spend,
)

__all__ = [
    "MIN_LENGTH_AFTER_SPEND_CM",
    "InsufficientLengthError",
    "SpendAction",
    "can_spend",
    "require_spend",
]
