"""Репозиторий блокировок (порт)."""

from __future__ import annotations

import abc
from datetime import datetime

from pipirik_wars.domain.security.entities import ActivityLock, LockReason


class IActivityLockRepository(abc.ABC):
    """Доступ к таблице `activity_locks`. Все методы — внутри `IUnitOfWork`."""

    @abc.abstractmethod
    async def try_acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        """Атомарно попытаться взять блок.

        Возвращает `True`, если запись создана; `False`, если у этого
        актора уже есть активная (НЕ-истёкшая) блокировка.
        """

    @abc.abstractmethod
    async def release(
        self,
        *,
        actor_kind: str,
        actor_id: int,
    ) -> None:
        """Снять блок, даже если он истёк. NO-OP, если записи нет."""

    @abc.abstractmethod
    async def get(
        self,
        *,
        actor_kind: str,
        actor_id: int,
    ) -> ActivityLock | None:
        """Прочитать текущую блокировку (включая истёкшую) или вернуть `None`."""
