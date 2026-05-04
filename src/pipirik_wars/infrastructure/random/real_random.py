"""Production-RNG.

Использует `secrets.SystemRandom` — достаточно качественное распределение
для игровой механики (не криптография, но не предсказуемое для игроков
из-за их собственных запросов).
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.shared.ports import IRandom

T = TypeVar("T")


class RealRandom(IRandom):
    """Системный RNG."""

    __slots__ = ("_rng",)

    def __init__(self) -> None:
        self._rng = secrets.SystemRandom()

    def randint(self, low: int, high: int) -> int:
        if low > high:
            raise ValueError("randint: low > high")
        return self._rng.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        if low > high:
            raise ValueError("uniform: low > high")
        return self._rng.uniform(low, high)

    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("choice from empty sequence")
        return self._rng.choice(items)

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        if not items:
            raise ValueError("weighted_choice from empty sequence")
        if len(items) != len(weights):
            raise ValueError("items and weights length mismatch")
        if any(w <= 0 for w in weights):
            raise ValueError("all weights must be positive")
        return self._rng.choices(list(items), weights=list(weights), k=1)[0]

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        if modulo <= 0:
            raise ValueError("modulo must be positive")
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % modulo
