"""In-memory реализация ``IPayoutLimitChecker`` для unit-тестов (Спринт 4.1-E).

По умолчанию — возвращает ``PayoutLimitWithin(remaining_native=sys.maxsize)``
для любых параметров (= лимит не превышен, unlimited-семантика).
Конфигурируется тремя независимыми способами:

* ``default_result: PayoutLimitCheckResult`` — что вернуть, если для пары
  ``(player_id, currency)`` нет точечного override-а.
* ``per_key: dict[tuple[int, Currency], PayoutLimitCheckResult]`` — точечные
  override-ы. Имеют приоритет над ``factory`` / ``default_result``.
* ``factory: Callable[[int, Currency, int, datetime], PayoutLimitCheckResult]``
  — программируемый callback. Если задан и в ``per_key`` нет точечного
  override-а, factory вызывается на каждом ``check(...)``.

Использование:

    # 1. Дефолтная unlimited-семантика (use-case-ам, у которых лимит не
    #    в фокусе теста):
    checker = FakePayoutLimitChecker()

    # 2. Force OverLimit для одного игрока + валюты:
    checker = FakePayoutLimitChecker(
        per_key={
            (player_id, Currency.USDT_DECIMAL): PayoutLimitOverLimit(
                retry_after=datetime(2026, 6, 11, tzinfo=UTC),
                exceeded_by_native=10,
            ),
        },
    )

    # 3. Программируемая логика по принципу «50 USDT за 30 дней»:
    def _factory(pid, ccy, amount, now):
        already = previous_claims.get((pid, ccy), 0)
        if already + amount <= 50_000_000:
            return PayoutLimitWithin(remaining_native=50_000_000 - already - amount)
        retry = oldest_claim_at + timedelta(days=30)
        return PayoutLimitOverLimit(retry_after=retry, exceeded_by_native=...)
    checker = FakePayoutLimitChecker(factory=_factory)

Поле ``calls`` хранит append-only лог вызовов для assert-ов в тестах
(``ClaimPrize``-use-case-а E.10 и ``EvaluatePayoutLimit``-use-case-а E.6).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.monetization.ports import IPayoutLimitChecker
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    PayoutLimitCheckResult,
    PayoutLimitWithin,
)


@dataclass(frozen=True, slots=True)
class FakePayoutLimitCheckCall:
    """Запись о вызове ``check(...)`` (для assert-ов в тестах)."""

    player_id: int
    currency: Currency
    amount_native: int
    now: datetime


_FactoryFn = Callable[[int, Currency, int, datetime], PayoutLimitCheckResult]


@dataclass
class FakePayoutLimitChecker(IPayoutLimitChecker):
    """In-memory ``IPayoutLimitChecker`` для тестов.

    Поля:

    * ``default_result`` — дефолтный результат. По умолчанию ``Within(
      remaining_native=sys.maxsize)`` (unlimited).
    * ``per_key`` — точечные override-ы для пар ``(player_id, currency)``.
    * ``factory`` — программируемый callback. Если задан и нет точечного
      override-а в ``per_key`` — вызывается на каждом ``check(...)``.
    * ``calls`` — append-only лог переданных вызовов.
    """

    default_result: PayoutLimitCheckResult = field(
        default_factory=lambda: PayoutLimitWithin(remaining_native=sys.maxsize),
    )
    per_key: Mapping[tuple[int, Currency], PayoutLimitCheckResult] = field(
        default_factory=dict,
    )
    factory: _FactoryFn | None = None
    calls: list[FakePayoutLimitCheckCall] = field(default_factory=list)

    async def check(
        self,
        *,
        player_id: int,
        currency: Currency,
        amount_native: int,
        now: datetime,
    ) -> PayoutLimitCheckResult:
        """Вернуть запрограммированный результат и записать вызов в ``calls``.

        Приоритет (от высокого к низкому): ``per_key`` → ``factory`` →
        ``default_result``. Этот порядок позволяет тесту сначала задать
        факторию по умолчанию (например, «всегда within»), а потом
        override-нуть один случай в ``per_key`` (например, «у этого игрока
        OverLimit»), не переписывая factory.
        """
        self.calls.append(
            FakePayoutLimitCheckCall(
                player_id=player_id,
                currency=currency,
                amount_native=amount_native,
                now=now,
            ),
        )
        if (player_id, currency) in self.per_key:
            return self.per_key[(player_id, currency)]
        if self.factory is not None:
            return self.factory(player_id, currency, amount_native, now)
        return self.default_result
