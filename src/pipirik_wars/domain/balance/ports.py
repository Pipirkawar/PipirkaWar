"""Порт балансовой конфигурации.

Use-case-ы из `application/` зависят только от этого интерфейса; они
не знают, что снимок берётся из YAML — реализация
(`infrastructure/balance/loader.py`) подключается через DI в
composition root (`bot/main.py:Container`).
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.balance.config import BalanceConfig


class IBalanceConfig(abc.ABC):
    """Источник балансовой конфигурации.

    Все вызовы ``get()`` возвращают «текущий» снимок ``BalanceConfig``.
    После hot-reload (см. `YamlBalanceLoader.reload()`) внутренняя
    ссылка может смениться на новый объект, но старые `BalanceConfig`-
    объекты остаются валидными до тех пор, пока на них есть ссылки —
    это гарантируется тем, что `BalanceConfig` иммутабелен.
    """

    @abc.abstractmethod
    def get(self) -> BalanceConfig:
        """Текущий снимок конфигурации."""
