"""Сущности очереди регистраций."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class SignupQueueStatus(str, enum.Enum):
    """Статус записи в очереди.

    `WAITING` — ждёт места; `PROMOTED` — был поднят и зарегистрирован
    (запись остаётся в `audit_log`, из таблицы удаляется).
    """

    WAITING = "waiting"
    PROMOTED = "promoted"


@dataclass(frozen=True, slots=True)
class SignupQueueEntry:
    """Одна запись в очереди регистраций.

    `position` — 1-based, считается на чтение через `ROW_NUMBER` в репо;
    при enqueue заполняется уже после INSERT-а. `tg_id` — естественный
    ключ (UNIQUE), один и тот же игрок не может стоять в очереди дважды.
    """

    id: int | None
    tg_id: int
    username: str | None
    locale: str | None
    position: int
    enqueued_at: datetime
