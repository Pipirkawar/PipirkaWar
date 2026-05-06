"""Домен «Глава клана дня» (`/clan_head`, Спринт 2.3, ГДД §6.1).

Иронично-смешная мини-фича для атмосферы — один игрок клана раз в сутки
получает прибавку длины `uniform(1, 20)` см и публичную «коронацию»
с цитатой из каталога.

Триггер — гибридный (ГДД §6.1, Q4 v9):
1. Кнопка/команда `/clan_head` от любого участника клана.
2. Фоновый APScheduler-cron с per-clan `random_offset(0..24h)` от 00:00 МСК
   (детерминированный hash от `clan_id + date`).

Что наступит первым — то и побеждает. Идемпотентность по `(clan_id,
moscow_date)` гарантирует, что параллельные триггеры не дают двойного
назначения.

Этот пакет содержит **доменный слой** (Спринт 2.3.A): VO `DailyHeadAssignment`,
порты `IDailyHeadRepository` / `IDailyActivityRepository`, доменные ошибки
и чистый сервис `DailyHeadService.assign_or_get(...)`. Persistence-слой —
в `infrastructure/db/repositories/daily_head.py` (Спринт 2.3.B), use-case-ы
`RequestDailyHead` / `RunDailyHeadCron` — в `application/daily_head/`
(Спринт 2.3.C).
"""

from __future__ import annotations

from pipirik_wars.domain.daily_head.entities import (
    DailyHeadAssignment,
    DailyHeadSource,
)
from pipirik_wars.domain.daily_head.errors import (
    ClanQuoteCatalogEmptyError,
    DailyHeadAlreadyAssignedError,
    DailyHeadError,
    DailyHeadInsufficientActivityError,
)
from pipirik_wars.domain.daily_head.quote import (
    ALLOWED_QUOTE_TAGS,
    ClanQuoteTemplate,
)
from pipirik_wars.domain.daily_head.repositories import (
    IDailyActivityRepository,
    IDailyHeadRepository,
)
from pipirik_wars.domain.daily_head.scheduling import (
    compute_daily_head_cron_offset_minutes,
)
from pipirik_wars.domain.daily_head.services import DailyHeadService

__all__ = [
    "ALLOWED_QUOTE_TAGS",
    "ClanQuoteCatalogEmptyError",
    "ClanQuoteTemplate",
    "DailyHeadAlreadyAssignedError",
    "DailyHeadAssignment",
    "DailyHeadError",
    "DailyHeadInsufficientActivityError",
    "DailyHeadService",
    "DailyHeadSource",
    "IDailyActivityRepository",
    "IDailyHeadRepository",
    "compute_daily_head_cron_offset_minutes",
]
