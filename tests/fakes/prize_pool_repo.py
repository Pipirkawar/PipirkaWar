"""In-memory реализация `IPrizePoolRepository` для unit-тестов (Спринт 4.1-B).

Имитирует `SqlAlchemyPrizePoolRepository` (B.3):

* `get_current()` — возвращает свежий снапшот пула; на пустом репозитории
  даёт `PrizePool.empty()`.
* `apply_increment(currency, amount_native)` — атомарный inkrement балланса
  выбранной валюты. Поднимает `PrizePoolAmountInvariantError` через
  доменный `PrizePool.apply_increment(...)` если результат `< 0`.

Использование:

    repo = FakePrizePoolRepository()
    pool_after = await repo.apply_increment(
        currency=Currency.STARS,
        amount_native=10,
    )
    assert pool_after.stars.value == 10

Тесты use-case-а `RecordDonation` могут читать `repo.calls` напрямую
для проверки порядка / аргументов вызовов.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipirik_wars.domain.monetization.entities import PrizePool
from pipirik_wars.domain.monetization.ports import IPrizePoolRepository
from pipirik_wars.domain.monetization.value_objects import Currency


@dataclass(frozen=True, slots=True)
class FakePrizePoolApplyIncrementCall:
    """Запись о вызове `apply_increment` (для assert-ов в тестах)."""

    currency: Currency
    amount_native: int


@dataclass
class FakePrizePoolRepository(IPrizePoolRepository):
    """In-memory реализация для тестов use-case-ов.

    Поля:
    - `state` — текущий снапшот пула. Дефолт `PrizePool.empty()`.
    - `calls` — append-only лог вызовов `apply_increment(...)`. Полезно
      для assert-ов вида «`apply_increment` не был вызван при `donation == 0`».
    - `get_current_calls` — счётчик вызовов `get_current()`.
    """

    state: PrizePool = field(default_factory=PrizePool.empty)
    calls: list[FakePrizePoolApplyIncrementCall] = field(default_factory=list)
    get_current_calls: int = 0

    async def get_current(self) -> PrizePool:
        """Вернуть текущий снапшот пула."""
        self.get_current_calls += 1
        return self.state

    async def apply_increment(
        self,
        *,
        currency: Currency,
        amount_native: int,
    ) -> PrizePool:
        """Применить inkrement через доменный `PrizePool.apply_increment`."""
        self.calls.append(
            FakePrizePoolApplyIncrementCall(
                currency=currency,
                amount_native=amount_native,
            )
        )
        self.state = self.state.apply_increment(
            currency=currency,
            amount_native=amount_native,
        )
        return self.state
