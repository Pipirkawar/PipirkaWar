"""Порт-провайдер каталога забавных логов леса (ГДД §15, ПД 1.5.3).

Сам каталог хранится в `config/templates/forest_logs_<locale>.json` и
загружается infrastructure-адаптером `JsonForestLogTemplateProvider`.
Application-слой не знает про путь к файлу: ему нужна только
последовательность `ForestLogTemplate` для нужной локали.

Локаль приходит снаружи (резолвится `LocaleResolver`-ом в
`LocaleMiddleware`-е, см. Спринт 1.5.A; для фоновой job-ы — приходит
от `IPlayerLocaleResolver`, Спринт 1.5.F). Если каталог пуст для
запрошенной локали — провайдер обязан попытаться отдать каталог
fallback-локали (`"ru"`) либо бросить `ForestLogNoTemplatesError`
(защитный случай; prod-инвариант: каталог не пуст и содержит
≥ 300 шаблонов).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.forest import ForestLogTemplate


class IForestLogTemplateProvider(abc.ABC):
    """Источник каталога забавных логов леса."""

    @abc.abstractmethod
    def get_templates(self, *, locale: str) -> Sequence[ForestLogTemplate]:
        """Вернуть каталог шаблонов для локали.

        Гарантии адаптера:
        - результат не пуст (иначе `ForestLogNoTemplatesError`);
        - один и тот же inst-провайдер для одного и того же locale
          возвращает идентичную последовательность (между reload-ами
          конфигурации возможно изменение).
        """


__all__ = ["IForestLogTemplateProvider"]
