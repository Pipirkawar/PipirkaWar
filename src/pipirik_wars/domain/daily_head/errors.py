"""Domain-ошибки «Главы клана дня» (Спринт 2.3)."""

from __future__ import annotations

from datetime import date

from pipirik_wars.shared.errors import DomainError


class DailyHeadError(DomainError):
    """Базовая ошибка «Главы клана дня»."""


class DailyHeadInsufficientActivityError(DailyHeadError):
    """В клане слишком мало «активных за N дней» участников.

    Бросается доменным сервисом `DailyHeadService.assign_or_get(...)`
    когда `len(active_member_ids) < daily_head.min_active_members`
    (по умолчанию 5). Use-case `RequestDailyHead` перехватывает эту
    ошибку и показывает игроку локализованное сообщение, cron же
    тихо пропускает клан до следующих суток.
    """

    __slots__ = ("active_count", "clan_id", "required")

    def __init__(self, *, clan_id: int, active_count: int, required: int) -> None:
        super().__init__(
            f"clan_id={clan_id} has only {active_count} active member(s), "
            f"but daily_head requires at least {required}"
        )
        self.clan_id = clan_id
        self.active_count = active_count
        self.required = required


class DailyHeadAlreadyAssignedError(DailyHeadError):
    """На сегодня (`moscow_date`) глава клана уже назначен.

    Бросается `DailyHeadService.assign(...)`, если в репозитории уже
    есть запись на `(clan_id, moscow_date)`. Use-case-ы 2.3.C
    (`RequestDailyHead` / `RunDailyHeadCron`) сначала зовут
    `assign_or_get(...)` — он сам обрабатывает эту ситуацию и не
    бросает наружу. Эта ошибка нужна для прямого `assign(...)`-вызова
    (когда вызывающий код **уверен**, что назначения нет — например,
    в тестах).
    """

    __slots__ = ("clan_id", "moscow_date")

    def __init__(self, *, clan_id: int, moscow_date: date) -> None:
        super().__init__(
            f"clan_id={clan_id} already has daily head on moscow_date={moscow_date.isoformat()}"
        )
        self.clan_id = clan_id
        self.moscow_date = moscow_date


__all__ = [
    "DailyHeadAlreadyAssignedError",
    "DailyHeadError",
    "DailyHeadInsufficientActivityError",
]
