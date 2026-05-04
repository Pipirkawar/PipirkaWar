"""Доменная подсистема безопасности.

`ActivityLock` — анти-дубль на одновременные действия одного актора
(`(actor_kind, actor_id)`). Применяется ко всем мутирующим командам
(лес, оракул, рейд, передача см и т.п.) — гарантирует, что у игрока
не может быть двух активных операций одновременно.

ГДД §0 (целостность данных), `development_plan.md` Спринт 0.2.1.
"""

from pipirik_wars.domain.security.entities import ActivityLock, LockReason
from pipirik_wars.domain.security.errors import LockAlreadyHeldError
from pipirik_wars.domain.security.repositories import IActivityLockRepository

__all__ = [
    "ActivityLock",
    "IActivityLockRepository",
    "LockAlreadyHeldError",
    "LockReason",
]
