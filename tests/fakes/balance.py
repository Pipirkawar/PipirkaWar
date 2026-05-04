"""Фейк `IBalanceConfig`: возвращает заранее переданный снимок.

Используется в unit-тестах application-слоя (Спринт 1.1+), где не
нужен реальный YAML-loader.
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig


class FakeBalanceConfig(IBalanceConfig):
    """In-memory снимок `BalanceConfig` без I/O."""

    __slots__ = ("_snapshot",)

    def __init__(self, snapshot: BalanceConfig) -> None:
        self._snapshot = snapshot

    def get(self) -> BalanceConfig:
        return self._snapshot

    def set(self, snapshot: BalanceConfig) -> None:
        """Подменить снимок (имитация hot-reload в тестах)."""
        self._snapshot = snapshot
