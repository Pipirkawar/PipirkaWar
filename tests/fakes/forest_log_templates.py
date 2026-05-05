"""In-memory `IForestLogTemplateProvider` для unit-тестов."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.forest import IForestLogTemplateProvider
from pipirik_wars.domain.forest import ForestLogTemplate


@dataclass
class FakeForestLogTemplateProvider(IForestLogTemplateProvider):
    """In-memory provider шаблонов forest-логов: per-locale заранее
    заданный список. Fallback на `"ru"`, как и реальный JSON-провайдер.
    """

    catalog: dict[str, tuple[ForestLogTemplate, ...]] = field(default_factory=dict)

    def get_templates(self, *, locale: str) -> Sequence[ForestLogTemplate]:
        if locale in self.catalog:
            return self.catalog[locale]
        if "ru" in self.catalog:
            return self.catalog["ru"]
        return ()


__all__ = ["FakeForestLogTemplateProvider"]
