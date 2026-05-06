"""In-memory реализация `IClanQuoteTemplateProvider` для unit-тестов (Спринт 2.3.E)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.daily_head import IClanQuoteTemplateProvider
from pipirik_wars.domain.daily_head import ClanQuoteTemplate


@dataclass
class FakeClanQuoteTemplateProvider(IClanQuoteTemplateProvider):
    """In-memory provider шаблонов цитат: per-locale заранее заданный список.

    Поведение зеркалит реальный `JsonClanQuoteTemplateProvider`
    (lazy-cache + fallback на `"ru"`). Для тестов handler-а 2.3.E
    используется в DI вместо JSON-загрузчика.
    """

    catalog: dict[str, tuple[ClanQuoteTemplate, ...]] = field(default_factory=dict)

    def get_templates(self, *, locale: str) -> Sequence[ClanQuoteTemplate]:
        if locale in self.catalog:
            return self.catalog[locale]
        if "ru" in self.catalog:
            return self.catalog["ru"]
        return ()


__all__ = ["FakeClanQuoteTemplateProvider"]
