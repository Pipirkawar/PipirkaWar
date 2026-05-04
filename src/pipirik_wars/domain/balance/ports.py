"""Порты балансовой конфигурации.

Use-case-ы из `application/` зависят только от этих интерфейсов; они
не знают, что снимок берётся из YAML — реализация
(`infrastructure/balance/loader.py`) подключается через DI в
composition root (`bot/main.py:Container`).

Два **разделённых** контракта (Interface Segregation Principle):

- `IBalanceConfig` — *чтение*. Подавляющее большинство use-case-ов
  (`RegisterPlayer`, `Forest`, `Oracle`, `UpgradeThickness`, …)
  получают только этот порт; они не должны иметь возможности
  «случайно» перечитать файл.
- `IBalanceReloader` — *обновление кэша*. Только админский use-case
  `ReloadBalance` (Спринт 1.1.8) получает этот порт.
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.balance.config import BalanceConfig


class IBalanceConfig(abc.ABC):
    """Источник балансовой конфигурации (read-only).

    Все вызовы ``get()`` возвращают «текущий» снимок ``BalanceConfig``.
    После hot-reload (см. `IBalanceReloader.reload()`) внутренняя
    ссылка может смениться на новый объект, но старые `BalanceConfig`-
    объекты остаются валидными до тех пор, пока на них есть ссылки —
    это гарантируется тем, что `BalanceConfig` иммутабелен.
    """

    @abc.abstractmethod
    def get(self) -> BalanceConfig:
        """Текущий снимок конфигурации."""


class IBalanceReloader(abc.ABC):
    """Порт hot-reload-а балансовой конфигурации.

    Отдельный интерфейс от `IBalanceConfig` — нужен только админскому
    use-case-у `ReloadBalance` (Спринт 1.1.8). Реализация атомарно
    перечитывает источник и подменяет кэш; в случае ошибки старый
    снимок остаётся валидным (см. `YamlBalanceLoader.reload`).
    """

    @abc.abstractmethod
    def reload(self) -> BalanceConfig:
        """Перечитать источник и подменить кэшированный снимок.

        Возвращает новый `BalanceConfig`. При ошибке чтения/валидации —
        бросает `ConfigError` (см. `shared.errors`); прежний снимок
        остаётся доступным через `IBalanceConfig.get()`.
        """
