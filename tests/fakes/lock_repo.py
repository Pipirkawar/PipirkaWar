"""In-memory реализация `IActivityLockRepository`.

Дублирует поведение `SqlAlchemyActivityLockRepository`:
- PK = `(actor_kind, actor_id)`;
- `try_acquire` отдаёт `False`, если активная (НЕ-истёкшая) запись уже
  есть; иначе создаёт/перезаписывает запись и возвращает `True`;
- `release` удаляет запись (NO-OP, если её не было).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.security import (
    ActivityLock,
    IActivityLockRepository,
    LockReason,
)


@dataclass
class FakeActivityLockRepository(IActivityLockRepository):
    """In-memory реализация для тестов."""

    locks: dict[tuple[str, int], ActivityLock] = field(default_factory=dict)

    async def try_acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        key = (actor_kind, actor_id)
        existing = self.locks.get(key)
        if existing is not None and not existing.is_expired(now=now):
            return False
        self.locks[key] = ActivityLock(
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=reason,
            acquired_at=now,
            expires_at=expires_at,
        )
        return True

    async def release(self, *, actor_kind: str, actor_id: int) -> None:
        self.locks.pop((actor_kind, actor_id), None)

    async def get(
        self,
        *,
        actor_kind: str,
        actor_id: int,
    ) -> ActivityLock | None:
        return self.locks.get((actor_kind, actor_id))
