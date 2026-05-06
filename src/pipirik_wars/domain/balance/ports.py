"""Порты балансовой конфигурации.

Use-case-ы из `application/` зависят только от этих интерфейсов; они
не знают, что снимок берётся из YAML — реализация
(`infrastructure/balance/loader.py`) подключается через DI в
composition root (`bot/main.py:Container`).

Три **разделённых** контракта (Interface Segregation Principle):

- `IBalanceConfig` — *чтение*. Подавляющее большинство use-case-ов
  (`RegisterPlayer`, `Forest`, `Oracle`, `UpgradeThickness`, …)
  получают только этот порт; они не должны иметь возможности
  «случайно» перечитать файл.
- `IBalanceReloader` — *обновление кэша*. Только админский use-case
  `ReloadBalance` (Спринт 1.1.8) получает этот порт.
- `IBalanceWriter` — *запись* в источник (Спринт 2.5-C.4). Получает
  только админский use-case `SetBalanceValue` (TOTP-обязательный).
  Atomic-write + автоматический `reload()` после успешной записи.
"""

from __future__ import annotations

import abc
from typing import Any

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


class IBalanceWriter(abc.ABC):
    """Порт записи балансового значения в источник (Спринт 2.5-C.4, ГДД §16).

    Используется **только** админским use-case `SetBalanceValue`.
    Контракт: атомарная запись (`tmp + os.replace`) + last-write-wins
    для одновременных вызовов из нескольких инстансов бота. После
    успешной записи реализация **обязана** обновить кэш `IBalanceConfig`
    (вызвать `reload()` под капотом).

    Атомарность: если применение значения приводит к невалидному
    `BalanceConfig` (нарушены pydantic-инварианты), реализация бросает
    `ConfigError` **до** записи на диск — старая версия файла не
    меняется.

    File-lock semantics: реализация может (но не обязана) использовать
    advisory file-lock (`fcntl.flock` на Linux) для сериализации
    одновременных записей; на платформах без `fcntl` (Windows)
    допустимо обходиться без lock-а — у нас 1 инстанс бота.
    """

    @abc.abstractmethod
    def write_value(self, *, key: str, raw_value: Any) -> BalanceConfig:
        """Установить значение по dotted-`key` и сохранить файл.

        :param key: dotted-path в YAML (например, ``forest.cooldown_min_minutes``).
            Точкой разделяются ключи mapping-ов; для списков допустим
            индекс (``items_catalog.0.id``). Поддерживаются YAML-alias-ы
            pydantic-полей (``display_names.0.from`` ↔ ``from_cm``).
        :param raw_value: новое значение в «сыром» виде (тип, который
            получил handler из Telegram-CLI). Реализация типизирует
            его через pydantic-схему `BalanceConfig`.
        :return: новый снимок `BalanceConfig` (после `reload()`).
        :raises BalanceKeyError: ключ не существует / неверная индексация.
        :raises ConfigError: применение значения нарушило бы pydantic-
            инвариант `BalanceConfig` (например, отрицательный `cost_base`).
        """
