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


class ClanQuoteCatalogEmptyError(DailyHeadError):
    """Каталог цитат «Главы клана дня» пуст для запрошенной локали и fallback-локали (RU).

    Бросается infrastructure-адаптером `JsonClanQuoteTemplateProvider`
    (Спринт 2.3.D), когда ни в `clan_quotes_<locale>.json`, ни в
    `clan_quotes_ru.json` нет шаблонов. Прод-инвариант: RU-каталог
    должен быть всегда (≥ 100 цитат, ПД §5 / 2.3.4); ошибка означает
    деплоймент-проблему.
    """

    __slots__ = ("locale",)

    def __init__(self, *, locale: str) -> None:
        super().__init__(
            f"clan quotes catalog is empty for locale={locale!r} (and RU fallback also empty/missing)"
        )
        self.locale = locale


__all__ = [
    "ClanQuoteCatalogEmptyError",
    "DailyHeadAlreadyAssignedError",
    "DailyHeadError",
    "DailyHeadInsufficientActivityError",
]
