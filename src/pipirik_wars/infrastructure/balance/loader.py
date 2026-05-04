"""YAML-loader балансовой конфигурации.

Реализация `IBalanceConfig`. Читает `config/balance.yaml`, валидирует
pydantic-схемой `BalanceConfig` и держит снимок в памяти.

Singleton-семантика — за DI: один `YamlBalanceLoader` создаётся в
composition root (`bot/main.py:build_container`) и пробрасывается
use-case-ам через `Container`. Класс сам по себе **не** делает
себя global-singleton-ом.

Любая ошибка чтения / парсинга / валидации → `ConfigError` (slой
``shared``). Это даёт админу единое место маппинга на «балансовый
файл невалиден» в логах / алёртах.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig, IBalanceReloader
from pipirik_wars.shared.errors import ConfigError


class YamlBalanceLoader(IBalanceConfig, IBalanceReloader):
    """Lazy-кэширующий loader `BalanceConfig` из YAML-файла.

    Реализует оба порта (`IBalanceConfig` — чтение, `IBalanceReloader`
    — hot-reload), но в DI прокидывается отдельно: read-only use-case-ы
    получают только `IBalanceConfig`, админский use-case
    `ReloadBalance` — `IBalanceReloader`.
    """

    __slots__ = ("_cached", "_path")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: BalanceConfig | None = None

    @property
    def path(self) -> Path:
        return self._path

    def get(self) -> BalanceConfig:
        """Текущий снимок. Первый вызов читает и валидирует файл.

        Последующие вызовы возвращают кэшированный объект до `reload()`.
        """
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    def reload(self) -> BalanceConfig:
        """Перечитать файл и атомарно подменить кэш.

        Возвращает новый снимок. Старый объект (если кто-то держит
        на него ссылку) остаётся валидным — `BalanceConfig` иммутабелен.
        """
        new = self._load()
        self._cached = new
        return new

    def _load(self) -> BalanceConfig:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"failed to read {self._path}: {e}") from e
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ConfigError(f"invalid YAML in {self._path}: {e}") from e
        if not isinstance(raw, dict):
            raise ConfigError(
                f"{self._path}: root must be a YAML mapping, got {type(raw).__name__}"
            )
        try:
            return BalanceConfig.model_validate(raw)
        except ValidationError as e:
            raise ConfigError(f"invalid balance config in {self._path}: {e}") from e
