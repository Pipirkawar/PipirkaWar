"""Детерминистичный RNG, инициализируемый seed-ом (Спринт 3.2-C).

В отличие от :class:`RealRandom` (использует `secrets.SystemRandom`,
непредсказуемо для игроков), :class:`SeededRandom` использует
`random.Random(seed)` — детерминированно от int-seed-а.

Зачем нужно: домен-сервис :func:`resolve_caravan_battle` требует
:class:`IRandom` для рандомизации блоков/ударов/назначения Атамана,
но результат боя должен быть **воспроизводим** при одном и том же
`caravan.random_seed` (для post-mortem audit-а и unit-тестов
use-case-а `FinishCaravanBattle`).

Use-case `FinishCaravanBattle` получает в конструкторе
`random_factory: Callable[[int], IRandom]`. В production
DI (`bot/main.py`, Спринт 3.2-C / C.8) фабрика — `SeededRandom`;
в unit-тестах use-case-а — :class:`tests.fakes.random.FakeRandom`.

NB: реализация **не криптографически стойкая**, но это и не нужно:
seed уже хранится открыто в `caravans.random_seed`, и игроки могут
посчитать исход самостоятельно по public-параметрам — это by design
для прозрачности боя.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.shared.ports import IRandom

T = TypeVar("T")


class SeededRandom(IRandom):
    """Детерминированный RNG на :class:`random.Random` от int-seed-а."""

    __slots__ = ("_rng",)

    def __init__(self, seed: int) -> None:
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
