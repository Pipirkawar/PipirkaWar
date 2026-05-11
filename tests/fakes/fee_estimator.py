"""In-memory реализация `IFeeEstimator` для unit-тестов (Спринт 4.1-C).

По умолчанию — возвращает `0` для всех валют (no-fee). Можно настроить
конкретные значения через `fees: dict[Currency, int]` или `factory`-
функцию, чтобы протестировать сценарии «комиссия > таргет» / «комиссия
зависит от валюты».

Использование:

    estimator = FakeFeeEstimator()  # all fees = 0
    estimator = FakeFeeEstimator(fees={Currency.TON_NANO: 1_000_000})
    estimator = FakeFeeEstimator(factory=lambda c, target: target // 100)

`calls` хранит лог переданных `(currency, target_amount_native)`-пар
для assert-ов в тестах use-case-а `GeneratePrizeLots`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pipirik_wars.domain.monetization.ports import IFeeEstimator
from pipirik_wars.domain.monetization.value_objects import Currency


@dataclass
class FakeFeeEstimator(IFeeEstimator):
    """In-memory `IFeeEstimator`.

    Поля:
    - `fees` — словарь фиксированных комиссий per currency. Дефолт пуст
      (комиссия `0` для всех валют).
    - `factory` — опциональный callback `(currency, target) -> int` для
      динамической оценки. Если задан — приоритетен над `fees`.
    - `calls` — append-only лог `(currency, target_amount_native)`-вызовов.
    """

    fees: Mapping[Currency, int] = field(default_factory=dict)
    factory: Callable[[Currency, int], int] | None = None
    calls: list[tuple[Currency, int]] = field(default_factory=list)

    async def estimate_fee(
        self,
        *,
        currency: Currency,
        target_amount_native: int,
    ) -> int:
        """Вернуть оценку комиссии. По дефолту — `0`."""
        self.calls.append((currency, target_amount_native))
        if self.factory is not None:
            return self.factory(currency, target_amount_native)
        return self.fees.get(currency, 0)
