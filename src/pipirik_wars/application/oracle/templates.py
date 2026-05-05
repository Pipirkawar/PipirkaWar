"""Порт-провайдер каталога предсказаний (`/oracle`).

Сам каталог хранится в `config/templates/oracle_<locale>.json` и
загружается infrastructure-адаптером `JsonOracleTemplateProvider`.
Application-слой не знает про путь к файлу: ему нужна только
последовательность `OracleTemplate` для нужной локали.

Локаль приходит снаружи (Спринт 1.5 i18n; пока handler передаёт
`"ru"` из `LocaleMiddleware`). Если каталог пуст для запрошенной
локали — провайдер обязан попытаться отдать каталог fallback-локали
(`"ru"`) либо бросить `OracleNoTemplatesError` (защитный случай;
prod-инвариант — каталог не пуст).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.oracle import OracleTemplate


class IOracleTemplateProvider(abc.ABC):
    """Источник каталога предсказаний."""

    @abc.abstractmethod
    def get_templates(self, *, locale: str) -> Sequence[OracleTemplate]:
        """Вернуть каталог шаблонов для локали.

        Гарантии адаптера:
        - результат не пуст;
        - один и тот же inst-провайдер для одного и того же locale
          возвращает идентичную последовательность (между reload-ами
          конфигурации возможно изменение, см. Спринт 1.5).
        """


__all__ = ["IOracleTemplateProvider"]
