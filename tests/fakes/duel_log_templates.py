"""In-memory `IDuelLogTemplateProvider` для unit-тестов."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.pvp import IDuelLogTemplateProvider
from pipirik_wars.domain.pvp import DuelLogTemplate


@dataclass
class FakeDuelLogTemplateProvider(IDuelLogTemplateProvider):
    """In-memory provider PvP-раунд-flavour-шаблонов: per-locale заранее
    заданный список. Fallback на `"ru"`, как и реальный JSON-провайдер.
    """

    catalog: dict[str, tuple[DuelLogTemplate, ...]] = field(default_factory=dict)

    def get_templates(self, *, locale: str) -> Sequence[DuelLogTemplate]:
        if locale in self.catalog:
            return self.catalog[locale]
        if "ru" in self.catalog:
            return self.catalog["ru"]
        return ()


__all__ = ["FakeDuelLogTemplateProvider"]
