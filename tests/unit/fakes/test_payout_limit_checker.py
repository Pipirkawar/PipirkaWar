"""Тесты ``FakePayoutLimitChecker`` (Спринт 4.1-E, шаг E.5).

Покрывают:

* default-результат (unlimited-семантика);
* конфигурируемый ``default_result``;
* точечные ``per_key``-override-ы;
* программируемая ``factory``;
* приоритет ``per_key`` > ``factory`` > ``default_result``;
* лог ``calls`` для assert-ов в тестах use-case-ов.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    PayoutLimitOverLimit,
    PayoutLimitWithin,
)
from tests.fakes.payout_limit_checker import (
    FakePayoutLimitCheckCall,
    FakePayoutLimitChecker,
)

_NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_default_result_is_unlimited_within() -> None:
    """По умолчанию возвращает ``Within(remaining_native=sys.maxsize)``."""
    checker = FakePayoutLimitChecker()
    result = await checker.check(
        player_id=1,
        currency=Currency.TON_NANO,
        amount_native=100,
        now=_NOW,
    )
    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == sys.maxsize


@pytest.mark.asyncio
async def test_custom_default_result_used() -> None:
    custom = PayoutLimitWithin(remaining_native=42)
    checker = FakePayoutLimitChecker(default_result=custom)
    result = await checker.check(
        player_id=1,
        currency=Currency.TON_NANO,
        amount_native=100,
        now=_NOW,
    )
    assert result == custom


@pytest.mark.asyncio
async def test_per_key_override_takes_priority() -> None:
    """``per_key`` имеет приоритет над ``default_result`` и ``factory``."""
    over = PayoutLimitOverLimit(retry_after=_NOW, exceeded_by_native=7)
    checker = FakePayoutLimitChecker(
        per_key={(42, Currency.USDT_DECIMAL): over},
        factory=lambda *_args: PayoutLimitWithin(remaining_native=0),
    )

    # Точечный ключ срабатывает.
    overridden = await checker.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10,
        now=_NOW,
    )
    assert overridden == over

    # Другой игрок попадает в factory (Within remaining=0).
    other = await checker.check(
        player_id=43,
        currency=Currency.USDT_DECIMAL,
        amount_native=10,
        now=_NOW,
    )
    assert isinstance(other, PayoutLimitWithin)
    assert other.remaining_native == 0


@pytest.mark.asyncio
async def test_factory_seen_when_no_per_key_match() -> None:
    """``factory`` срабатывает при отсутствии точечного override-а."""

    def _factory(
        player_id: int,
        currency: Currency,
        amount_native: int,
        now: datetime,
    ) -> PayoutLimitWithin:
        return PayoutLimitWithin(remaining_native=player_id + amount_native)

    checker = FakePayoutLimitChecker(factory=_factory)
    result = await checker.check(
        player_id=5,
        currency=Currency.TON_NANO,
        amount_native=3,
        now=_NOW,
    )
    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 8


@pytest.mark.asyncio
async def test_calls_log_records_each_invocation() -> None:
    checker = FakePayoutLimitChecker()
    await checker.check(
        player_id=1,
        currency=Currency.TON_NANO,
        amount_native=10,
        now=_NOW,
    )
    await checker.check(
        player_id=2,
        currency=Currency.USDT_DECIMAL,
        amount_native=20,
        now=_NOW,
    )

    assert checker.calls == [
        FakePayoutLimitCheckCall(
            player_id=1,
            currency=Currency.TON_NANO,
            amount_native=10,
            now=_NOW,
        ),
        FakePayoutLimitCheckCall(
            player_id=2,
            currency=Currency.USDT_DECIMAL,
            amount_native=20,
            now=_NOW,
        ),
    ]
