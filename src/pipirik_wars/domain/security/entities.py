"""Доменные сущности подсистемы безопасности."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class LockReason(str, enum.Enum):
    """За что был взят блок.

    Не influence-полный список — value-объект с открытым множеством,
    но enum даёт IDE-completion и защиту от опечаток.
    """

    FOREST = "forest"
    MOUNTAINS = "mountains"
    DUNGEON = "dungeon"
    ORACLE = "oracle"
    RAID = "raid"
    CARAVAN = "caravan"
    PVP = "pvp"
    THICKNESS_UPGRADE = "thickness_upgrade"
    DAILY_HEAD = "daily_head"
    ADMIN_ACTION = "admin_action"


@dataclass(frozen=True, slots=True)
class ActivityLock:
    """Активная блокировка действий актора.

    Существует в БД ровно одна запись на `(actor_kind, actor_id)`:
    Postgres-уровневый PRIMARY KEY гарантирует это. При попытке
    повторного захвата — `INSERT ... ON CONFLICT DO NOTHING` возвращает
    0 строк, и use-case бросает `LockAlreadyHeldError`.

    `expires_at` — защита от «зависших» блокировок: если процесс
    упал между acquire и release, блок снимается автоматически
    после истечения TTL (в Спринте 1.1+ будет cron-zombie-killer).
    """

    actor_kind: str
    actor_id: int
    reason: LockReason
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at

    @classmethod
    def new(
        cls,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        ttl: timedelta,
    ) -> ActivityLock:
        if ttl.total_seconds() <= 0:
            raise ValueError("ActivityLock TTL must be positive")
        return cls(
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=reason,
            acquired_at=now,
            expires_at=now + ttl,
        )
