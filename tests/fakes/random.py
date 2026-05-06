"""Фейк RNG: детерминированный, на seed-Random.

Лучше, чем MagicMock с `side_effect=[...]`: тесты не зависят от
порядка вызовов внутри use-case. При смене реализации use-case
(например, добавился ещё один randint) тесты не ломаются на
«не хватило значений в side_effect».
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.shared.ports import IRandom

T = TypeVar("T")


class FakeRandom(IRandom):
    """In-memory RNG с фиксированным seed-ом."""

    __slots__ = ("_rng",)

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

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

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:
        if not items:
            raise ValueError("shuffle on empty sequence")
        buffer = list(items)
        self._rng.shuffle(buffer)
        return tuple(buffer)
