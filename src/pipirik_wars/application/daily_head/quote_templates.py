"""Порт-провайдер каталога цитат «Главы клана дня» (Спринт 2.3.D).

Сам каталог хранится в `config/templates/clan_quotes_<locale>.json` и
загружается infrastructure-адаптером `JsonClanQuoteTemplateProvider`.
Application-слой не знает про путь к файлу: ему нужна только
последовательность `ClanQuoteTemplate` для нужной локали.

Локаль приходит снаружи (Спринт 1.5 i18n; handler передаёт
резолвенную `Locale.value` из `LocaleMiddleware`). Если каталог пуст
для запрошенной локали — провайдер обязан попытаться отдать каталог
fallback-локали (`"ru"`) либо бросить `ClanQuoteCatalogEmptyError`
(защитный случай; prod-инвариант — RU-каталог не пуст).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.daily_head import ClanQuoteTemplate


class IClanQuoteTemplateProvider(abc.ABC):
    """Источник каталога цитат «Главы клана дня»."""

    @abc.abstractmethod
    def get_templates(self, *, locale: str) -> Sequence[ClanQuoteTemplate]:
        """Вернуть каталог шаблонов цитат для локали.

        Гарантии адаптера:
        - результат не пуст (иначе `ClanQuoteCatalogEmptyError`);
        - один и тот же inst-провайдер для одной и той же локали
          возвращает идентичную последовательность (между reload-ами
          конфигурации, см. Спринт 1.5, возможно изменение).
        """


__all__ = ["IClanQuoteTemplateProvider"]
