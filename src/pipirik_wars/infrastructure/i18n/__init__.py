"""Инфраструктура локализации — реализация портов `application.i18n`.

Спринт 1.5.A / ПД 1.5.1: Mozilla Fluent (`fluent.runtime`) поверх
`.ftl`-файлов в `locales/{ru,en}.ftl`.
"""

from pipirik_wars.infrastructure.i18n.fluent_bundle import FluentMessageBundle

__all__ = ["FluentMessageBundle"]
