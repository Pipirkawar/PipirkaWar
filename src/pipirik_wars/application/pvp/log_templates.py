"""Порт-провайдер каталога забавных раунд-логов PvP (ГДД §15, ПД 2.1.5, Спринт 2.1.H).

Сам каталог хранится в `config/templates/duel_logs_<locale>.json` и
загружается infrastructure-адаптером `JsonDuelLogTemplateProvider`.
Application-слой не знает про путь к файлу: ему нужна только
последовательность `DuelLogTemplate` для нужной локали.

Локаль приходит снаружи (резолвится `LocaleResolver`-ом в
`LocaleMiddleware`-е, см. Спринт 1.5.A). Если каталог пуст для
запрошенной локали — провайдер обязан попытаться отдать каталог
fallback-локали (`"ru"`) либо бросить `DuelLogNoTemplatesError`
(защитный случай; prod-инвариант: каталог не пуст и содержит
≥ 50 шаблонов).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.pvp import DuelLogTemplate


class IDuelLogTemplateProvider(abc.ABC):
    """Источник каталога забавных раунд-логов PvP."""

    @abc.abstractmethod
    def get_templates(self, *, locale: str) -> Sequence[DuelLogTemplate]:
        """Вернуть каталог шаблонов для локали.

        Гарантии адаптера:
        - результат не пуст (иначе `DuelLogNoTemplatesError`);
        - один и тот же inst-провайдер для одного и того же locale
          возвращает идентичную последовательность (между reload-ами
          конфигурации возможно изменение).
        """


__all__ = ["IDuelLogTemplateProvider"]
