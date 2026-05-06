"""Domain-сущности «Глава клана дня» (ГДД §6.1, ПД §6 / Спринт 2.3).

`DailyHeadAssignment` — иммутабельная запись таблицы `daily_heads`:
один (clan, moscow_date) → один назначенный игрок (`player_id`) с
бонусом `bonus_cm` ∈ [`balance.daily_head.bonus_min`,
`balance.daily_head.bonus_max`]. UNIQUE-индекс по `(clan_id,
moscow_date)` гарантирует идемпотентность по сутка-кланам.

`DailyHeadSource` — откуда пришло назначение: кнопка/команда от
участника клана (`BUTTON`) или фоновый APScheduler-cron (`CRON`).
В обоих случаях логика одна — `DailyHeadService.assign_or_get(...)` —
поле сохраняется только для аналитики «какой триггер сработал
первым».

Никаких side-эффектов в этом модуле: запись в `daily_heads`,
начисление длины через `progression.add_length(reason="daily_head")`
и аудит — это use-case `RequestDailyHead` / `RunDailyHeadCron`
(Спринт 2.3.C).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime


class DailyHeadSource(str, enum.Enum):
    """Триггер назначения главы клана дня (ГДД §6.1, гибридный).

    `BUTTON` — игрок нажал «🎲 Назначить главу дня» / зашёл `/clan_head`.
    `CRON` — фоновый APScheduler в `random_offset(0..24h)`-час с 00:00 МСК.

    Идемпотентность по `(clan_id, moscow_date)` означает, что какой
    бы триггер ни сработал первым, он и победит — повторный (любого
    типа) в те же сутки получит уже-назначенного главу.
    """

    BUTTON = "button"
    CRON = "cron"


@dataclass(frozen=True, slots=True)
class DailyHeadAssignment:
    """Назначение «Главы клана дня» — одна запись в `daily_heads`.

    Поля:
    - `id` — суррогатный PK (None до `add()`-а в репозитории).
    - `clan_id` — внутренний id клана (>= 1).
    - `player_id` — внутренний id игрока, ставшего главой (>= 1).
    - `moscow_date` — календарная дата по `Europe/Moscow`, в которую
      назначение действительно (унике с `clan_id`).
    - `source` — кто инициировал (см. `DailyHeadSource`).
    - `bonus_cm` — прибавка длины, выданная этому игроку (∈ [1, 20]
      по дефолтному балансу). Сохраняется на момент розыгрыша,
      чтобы аудит-лог сходился с `audit_log.bonus_cm`.
    - `assigned_at` — UTC-таймстамп момента назначения. По нему же
      строится «последние N назначений клана» для anti-repeat-фильтра
      (`avoid_last_n` из `DailyHeadConfig`).

    Инварианты:
    - все id-ы > 0 (или None для новой записи без PK);
    - `bonus_cm > 0` (баланс гарантирует `bonus_min > 0`);
    - `assigned_at.tzinfo is not None` (timezone-aware UTC).
    """

    id: int | None
    clan_id: int
    player_id: int
    moscow_date: date
    source: DailyHeadSource
    bonus_cm: int
    assigned_at: datetime

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError(f"DailyHeadAssignment.id must be positive or None, got {self.id}")
        if self.clan_id <= 0:
            raise ValueError(f"DailyHeadAssignment.clan_id must be positive, got {self.clan_id}")
        if self.player_id <= 0:
            raise ValueError(
                f"DailyHeadAssignment.player_id must be positive, got {self.player_id}"
            )
        if self.bonus_cm <= 0:
            raise ValueError(f"DailyHeadAssignment.bonus_cm must be positive, got {self.bonus_cm}")
        if self.assigned_at.tzinfo is None:
            raise ValueError("DailyHeadAssignment.assigned_at must be timezone-aware (UTC)")


__all__ = [
    "DailyHeadAssignment",
    "DailyHeadSource",
]
