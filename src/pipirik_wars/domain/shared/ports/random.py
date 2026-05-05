"""Источник случайности. Подменяется в тестах на детерминированный фейк.

Domain-код **никогда** не зовёт `random.*` напрямую — иначе тесты на
дроп лесных предметов, бонусы Главы клана и т.п. становятся «летающими»
(flaky). Вместо этого use-case получает `IRandom` через DI.

В Спринте 2.3 (Глава клана дня) `random_offset(0..24h)` per clan
вычисляется через `IRandom.deterministic_uint(seed)`, чтобы тесты
проходили воспроизводимо при одних и тех же входах.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class IRandom(abc.ABC):
    """Интерфейс генератора случайностей."""

    @abc.abstractmethod
    def randint(self, low: int, high: int) -> int:
        """Случайное целое в `[low, high]` (включительно с обоих сторон)."""

    @abc.abstractmethod
    def uniform(self, low: float, high: float) -> float:
        """Равномерное вещественное в `[low, high]`."""

    @abc.abstractmethod
    def choice(self, items: Sequence[T]) -> T:
        """Случайный элемент. Падает на пустой последовательности."""

    @abc.abstractmethod
    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        """Случайный элемент с заданными весами.

        `len(items)` и `len(weights)` должны совпадать; все веса > 0.
        Используется для веток исхода леса (`scarce/normal/abundant`).
        """

    @abc.abstractmethod
    def deterministic_uint(self, seed: str, modulo: int) -> int:
        """Детерминированный псевдослучайный `int` в `[0, modulo)` от `seed`.

        Не зависит от состояния генератора, всегда даёт один и тот же
        результат на одних и тех же входах. Используется для случаев,
        когда нужна воспроизводимость без хранения seed-а в БД
        (Глава клана дня: per-clan offset за сутки).
        """

    @abc.abstractmethod
    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:
        """Возвращает новый кортеж — равномерную случайную перестановку `items`.

        Иммутабельный аналог `random.shuffle` (не мутирует входной
        контейнер): домен оперирует frozen-tuple-ами, и in-place мутации
        не вписываются в чистые VO. Падает на пустой последовательности.

        Используется в массовом PvP (Спринт 2.2.B) для назначения
        случайных пар «атакующий → защитник». Детерминированный seed
        в тестах через :class:`tests.fakes.random.FakeRandom`.
        """
