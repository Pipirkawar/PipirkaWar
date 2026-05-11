"""Unit-тесты `InMemoryFeeEstimator` (Спринт 4.1-C, шаг C.7.a).

Контракт:
* `STARS` → всегда `0` (TG-сторона без gas-а).
* `TON_NANO` → `10_000_000` (0.01 TON, P95 plain-TON-перевода).
* `USDT_DECIMAL` → `200_000` (0.2 USDT, буфер на TON-газ jetton-перевода).
* `target_amount_native` игнорируется (константная оценка).
* Возврат всегда `int >= 0`; контракт `IFeeEstimator` соблюдён.
"""

from __future__ import annotations

import inspect

import pytest

from pipirik_wars.domain.monetization.ports import IFeeEstimator
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.fees import InMemoryFeeEstimator


def _assert_implements_protocol(estimator: IFeeEstimator) -> None:
    """Структурная проверка протокола: mypy --strict падает, если
    `InMemoryFeeEstimator` не удовлетворяет `IFeeEstimator`."""
    assert estimator is not None


class TestInMemoryFeeEstimatorConstants:
    """Каждая валюта возвращает свою задокументированную константу."""

    @pytest.mark.asyncio
    async def test_stars_returns_zero(self) -> None:
        estimator = InMemoryFeeEstimator()
        fee = await estimator.estimate_fee(
            currency=Currency.STARS,
            target_amount_native=100,
        )
        assert fee == 0

    @pytest.mark.asyncio
    async def test_ton_nano_returns_p95_buffer(self) -> None:
        # 10_000_000 nano-TON = 0.01 TON — P95 plain-TON-перевода.
        estimator = InMemoryFeeEstimator()
        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=500_000_000,
        )
        assert fee == 10_000_000

    @pytest.mark.asyncio
    async def test_usdt_decimal_returns_p95_buffer(self) -> None:
        # 200_000 USDT-decimal = 0.2 USDT — буфер на TON-газ jetton-перевода.
        estimator = InMemoryFeeEstimator()
        fee = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=1_000_000,
        )
        assert fee == 200_000


class TestInMemoryFeeEstimatorContract:
    """Контракт `IFeeEstimator`: возврат `int >= 0`, target игнорируется."""

    @pytest.mark.asyncio
    async def test_target_amount_native_is_ignored(self) -> None:
        # Контракт 4.1-C: оценка константна, не зависит от target.
        estimator = InMemoryFeeEstimator()
        fee_small = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=1,
        )
        fee_huge = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=10**18,
        )
        assert fee_small == fee_huge == 10_000_000

    @pytest.mark.asyncio
    async def test_all_currencies_return_non_negative_int(self) -> None:
        estimator = InMemoryFeeEstimator()
        for currency in Currency:
            fee = await estimator.estimate_fee(
                currency=currency,
                target_amount_native=1_000,
            )
            assert isinstance(fee, int)
            assert not isinstance(fee, bool)
            assert fee >= 0

    @pytest.mark.asyncio
    async def test_estimator_is_stateless_idempotent(self) -> None:
        # Повторный вызов с теми же параметрами возвращает тот же ответ.
        estimator = InMemoryFeeEstimator()
        first = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=5_000_000,
        )
        second = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=5_000_000,
        )
        assert first == second == 200_000

    def test_implements_ifee_estimator_protocol(self) -> None:
        # Структурная проверка: `_assert_implements_protocol` принимает
        # `IFeeEstimator`, mypy --strict ловит несоответствие.
        # `runtime_checkable` на порту не стоит (по дизайну), поэтому
        # isinstance-checks делать нельзя.
        estimator = InMemoryFeeEstimator()
        _assert_implements_protocol(estimator)

    def test_estimate_fee_is_coroutine(self) -> None:
        # Контракт порта — async-сигнатура (на 4.1-D понадобится HTTP).
        estimator = InMemoryFeeEstimator()
        assert inspect.iscoroutinefunction(estimator.estimate_fee)
