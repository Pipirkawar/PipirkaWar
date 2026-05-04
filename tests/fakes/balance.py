"""Фейк `IBalanceConfig` / `IBalanceReloader`: возвращает заранее переданный снимок.

Используется в unit-тестах application-слоя (Спринт 1.1+), где не
нужен реальный YAML-loader.

Реализует **оба** порта одной классой — это совпадает с production
(`YamlBalanceLoader` тоже реализует и `IBalanceConfig`, и
`IBalanceReloader`). Тесты, которым нужен только read-side, могут
игнорировать `reload()`; тесты `ReloadBalance` ставят следующий
снимок через `set(...)` и убеждаются, что после `reload()` именно
он становится «текущим».
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig, IBalanceReloader


class FakeBalanceConfig(IBalanceConfig, IBalanceReloader):
    """In-memory снимок `BalanceConfig` без I/O."""

    __slots__ = ("_next", "_snapshot")

    def __init__(self, snapshot: BalanceConfig) -> None:
        self._snapshot = snapshot
        self._next: BalanceConfig | None = None

    def get(self) -> BalanceConfig:
        return self._snapshot

    def set(self, snapshot: BalanceConfig) -> None:
        """Подменить снимок (имитация hot-reload в тестах).

        Меняет сразу и текущий, и «то, что вернёт следующий reload()».
        """
        self._snapshot = snapshot
        self._next = snapshot

    def queue_next_reload(self, snapshot: BalanceConfig) -> None:
        """Подложить снимок, который вернёт *следующий* `reload()`.

        Полезно для тестов: позволяет проверить, что use-case действительно
        зовёт `reload()` (а не использует уже текущий `get()`).
        """
        self._next = snapshot

    def reload(self) -> BalanceConfig:
        """Имитирует hot-reload: атомарно подменяет `_snapshot`.

        Если `queue_next_reload(...)` не звали — возвращает текущий
        снимок (как `YamlBalanceLoader`, перечитывающий тот же файл).
        """
        if self._next is not None:
            self._snapshot = self._next
        return self._snapshot
