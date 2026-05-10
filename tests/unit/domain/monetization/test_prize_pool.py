"""Тесты доменного агрегата `PrizePool` (ГДД §12.6, Спринт 4.1-B).

Покрывают:
* `PrizePool.empty()` — фабрика нулевого пула;
* `PrizePool.balance_for(currency)` — точечный accessor;
* `PrizePool.apply_increment(currency, amount_native)` — иммутабельный
  inc/dec с инвариантом `>= 0`;
* `PrizePoolAmountInvariantError` — ошибка при попытке увести в минус;
* immutability frozen-агрегата (нельзя мутировать поля).
"""

from __future__ import annotations

import dataclasses

import pytest

from pipirik_wars.domain.monetization import (
    Currency,
    PrizePool,
    PrizePoolAmountInvariantError,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)


class TestPrizePoolEmpty:
    """`PrizePool.empty()` — все три баланса нулевые."""

    def test_empty_returns_zero_balance(self) -> None:
        pool = PrizePool.empty()
        assert pool.stars.value == 0
        assert pool.ton_nano.value == 0
        assert pool.usdt_decimal.value == 0

    def test_two_empty_pools_compare_equal(self) -> None:
        assert PrizePool.empty() == PrizePool.empty()

    def test_empty_is_frozen(self) -> None:
        pool = PrizePool.empty()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pool.stars = StarsPoolBalance(10)


class TestPrizePoolBalanceFor:
    """`balance_for(currency)` — accessor по `Currency`-enum-значению."""

    def test_balance_for_stars(self) -> None:
        pool = PrizePool(
            stars=StarsPoolBalance(42),
            ton_nano=TonNanoAmount(0),
            usdt_decimal=UsdtDecimalAmount(0),
        )
        assert pool.balance_for(Currency.STARS) == 42

    def test_balance_for_ton_nano(self) -> None:
        pool = PrizePool(
            stars=StarsPoolBalance(0),
            ton_nano=TonNanoAmount(9_000_000_000),
            usdt_decimal=UsdtDecimalAmount(0),
        )
        assert pool.balance_for(Currency.TON_NANO) == 9_000_000_000

    def test_balance_for_usdt_decimal(self) -> None:
        pool = PrizePool(
            stars=StarsPoolBalance(0),
            ton_nano=TonNanoAmount(0),
            usdt_decimal=UsdtDecimalAmount(5_000_000),
        )
        assert pool.balance_for(Currency.USDT_DECIMAL) == 5_000_000


class TestPrizePoolApplyIncrement:
    """`apply_increment(currency, amount_native)` — иммутабельный inc/dec."""

    def test_zero_delta_returns_equal_pool(self) -> None:
        before = PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        after = before.apply_increment(Currency.STARS, 0)
        assert after == before
        # И всё-таки это новый VO (frozen + slots → equality по полям, но
        # `is`-сравнение различает инстансы).
        assert after is not before

    def test_positive_increment_stars(self) -> None:
        pool = PrizePool.empty().apply_increment(Currency.STARS, 100)
        assert pool.stars.value == 100
        assert pool.ton_nano.value == 0
        assert pool.usdt_decimal.value == 0

    def test_positive_increment_ton_nano(self) -> None:
        pool = PrizePool.empty().apply_increment(Currency.TON_NANO, 1_000_000_000)
        assert pool.stars.value == 0
        assert pool.ton_nano.value == 1_000_000_000
        assert pool.usdt_decimal.value == 0

    def test_positive_increment_usdt_decimal(self) -> None:
        pool = PrizePool.empty().apply_increment(Currency.USDT_DECIMAL, 1_000_000)
        assert pool.stars.value == 0
        assert pool.ton_nano.value == 0
        assert pool.usdt_decimal.value == 1_000_000

    def test_increments_accumulate_across_currencies(self) -> None:
        pool = (
            PrizePool.empty()
            .apply_increment(Currency.STARS, 100)
            .apply_increment(Currency.TON_NANO, 9_000_000_000)
            .apply_increment(Currency.USDT_DECIMAL, 5_000_000)
            .apply_increment(Currency.STARS, 25)
        )
        assert pool.stars.value == 125
        assert pool.ton_nano.value == 9_000_000_000
        assert pool.usdt_decimal.value == 5_000_000

    def test_immutability_original_pool_not_mutated(self) -> None:
        before = PrizePool.empty()
        before.apply_increment(Currency.STARS, 10)
        assert before == PrizePool.empty()  # original ↔ pristine

    def test_negative_increment_within_bounds_ok(self) -> None:
        before = PrizePool.empty().apply_increment(Currency.STARS, 100)
        after = before.apply_increment(Currency.STARS, -42)
        assert after.stars.value == 58

    def test_negative_increment_to_zero_ok(self) -> None:
        before = PrizePool.empty().apply_increment(Currency.TON_NANO, 1_000)
        after = before.apply_increment(Currency.TON_NANO, -1_000)
        assert after.ton_nano.value == 0

    def test_negative_increment_below_zero_raises(self) -> None:
        before = PrizePool.empty().apply_increment(Currency.STARS, 100)
        with pytest.raises(PrizePoolAmountInvariantError) as exc_info:
            before.apply_increment(Currency.STARS, -101)
        err = exc_info.value
        assert err.currency is Currency.STARS
        assert err.current_balance_native == 100
        assert err.attempted_delta_native == -101

    def test_negative_increment_below_zero_for_empty_pool_raises(self) -> None:
        with pytest.raises(PrizePoolAmountInvariantError) as exc_info:
            PrizePool.empty().apply_increment(Currency.USDT_DECIMAL, -1)
        err = exc_info.value
        assert err.currency is Currency.USDT_DECIMAL
        assert err.current_balance_native == 0
        assert err.attempted_delta_native == -1

    @pytest.mark.parametrize("bad", [1.5, "10", b"x", None, object()])
    def test_non_int_amount_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="amount_native must be int"):
            PrizePool.empty().apply_increment(Currency.STARS, bad)  # type: ignore[arg-type]

    def test_bool_amount_raises(self) -> None:
        with pytest.raises(TypeError, match="amount_native must be int"):
            PrizePool.empty().apply_increment(Currency.STARS, True)


class TestPrizePoolAmountInvariantError:
    """Атрибуты ошибки + сообщение."""

    def test_attributes(self) -> None:
        err = PrizePoolAmountInvariantError(
            currency=Currency.STARS,
            current_balance_native=10,
            attempted_delta_native=-50,
        )
        assert err.currency is Currency.STARS
        assert err.current_balance_native == 10
        assert err.attempted_delta_native == -50

    def test_message_contains_diagnostics(self) -> None:
        err = PrizePoolAmountInvariantError(
            currency=Currency.TON_NANO,
            current_balance_native=100,
            attempted_delta_native=-200,
        )
        msg = str(err)
        assert "ton_nano" in msg
        assert "current=100" in msg
        assert "attempted_delta=-200" in msg
        assert "would-become=-100" in msg


class TestPrizePoolEqualityAndHash:
    """frozen+slots-агрегат хэшируем и сравниваем по полям."""

    def test_equality_by_fields(self) -> None:
        a = PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        b = PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_by_any_field(self) -> None:
        base = PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        assert base != PrizePool(
            stars=StarsPoolBalance(11),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        assert base != PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(21),
            usdt_decimal=UsdtDecimalAmount(30),
        )
        assert base != PrizePool(
            stars=StarsPoolBalance(10),
            ton_nano=TonNanoAmount(20),
            usdt_decimal=UsdtDecimalAmount(31),
        )
