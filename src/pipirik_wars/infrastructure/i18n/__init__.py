"""Инфраструктура локализации — реализация портов `application.i18n`.

Спринт 1.5.A / ПД 1.5.1: Mozilla Fluent (`fluent.runtime`) поверх
`.ftl`-файлов в `locales/{ru,en}.ftl`.
Спринт 1.5.F / ПД 1.5.2: `PlayerLocaleResolverDB` — резолвер
`Locale` для фоновых jobs / middleware-а.
"""

from pipirik_wars.infrastructure.i18n.fluent_bundle import FluentMessageBundle
from pipirik_wars.infrastructure.i18n.player_locale import PlayerLocaleResolverDB

__all__ = ["FluentMessageBundle", "PlayerLocaleResolverDB"]
