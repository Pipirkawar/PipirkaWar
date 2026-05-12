"""Unit-тесты `TonRpcFeeEstimator` (Спринт 4.1-D, шаг D.5).

Контракт `IFeeEstimator`:
* `STARS` → всегда `0` (TG-сторона без газа).
* `TON_NANO` / `USDT_DECIMAL` → P95 (nearest-rank) от
  `client.recent_fees(address, days)`.
* Пустая выборка → fallback из настроек.
* Сетевые ошибки пробрасываются наверх.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.monetization.ports import IFeeEstimator
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc.client import RecentFee
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    TonRpcCallError,
    TonRpcTimeoutError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.fee_estimator import (
    TonRpcFeeEstimator,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from tests.unit.infrastructure.payments.ton_rpc._fakes import FakeTonRpcClient

_FAKE_PAYOUT_WALLET = "0:3333333333333333333333333333333333333333333333333333333333333333"
_FAKE_USDT_MASTER = "EQAusdtmasterzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"


def _make_settings(**overrides: object) -> TonRpcSettings:
    defaults: dict[str, object] = {
        "endpoint": "https://testnet.example.com/api/v2",
        "is_sandbox": True,
        "usdt_jetton_master": _FAKE_USDT_MASTER,
        "payout_wallet_address": _FAKE_PAYOUT_WALLET,
        "request_timeout_seconds": 10.0,
        "fee_window_days": 7,
        "fallback_fee_buffer_ton_nano": 10_000_000,
        "fallback_fee_buffer_usdt_decimal": 200_000,
    }
    defaults.update(overrides)
    return TonRpcSettings(**defaults)  # type: ignore[arg-type]


def _fees_at(values: list[int]) -> list[RecentFee]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        RecentFee(fee_native=v, occurred_at=base + timedelta(hours=i)) for i, v in enumerate(values)
    ]


def _assert_implements_protocol(estimator: IFeeEstimator) -> None:
    """Структурная проверка протокола: mypy --strict падает, если
    `TonRpcFeeEstimator` не удовлетворяет `IFeeEstimator`."""
    assert estimator is not None


class TestTonRpcFeeEstimatorStars:
    @pytest.mark.asyncio
    async def test_stars_returns_zero(self) -> None:
        estimator = TonRpcFeeEstimator(client=FakeTonRpcClient(), settings=_make_settings())
        fee = await estimator.estimate_fee(
            currency=Currency.STARS,
            target_amount_native=100,
        )
        assert fee == 0

    @pytest.mark.asyncio
    async def test_stars_does_not_touch_client(self) -> None:
        client = FakeTonRpcClient()
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())
        await estimator.estimate_fee(currency=Currency.STARS, target_amount_native=10**9)
        assert client.calls_recent_fees == []


class TestTonRpcFeeEstimatorTonNano:
    @pytest.mark.asyncio
    async def test_ton_nano_returns_p95_of_history(self) -> None:
        # P95 of [10..100 step 10] (10 элементов): nearest-rank ⇒
        # sorted_asc[ceil(0.95 * 10) - 1] = sorted_asc[10 - 1] = 100.
        client = FakeTonRpcClient()
        client.set_recent_fees(
            address=_FAKE_PAYOUT_WALLET,
            fees=_fees_at([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        )
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=500_000_000,
        )

        assert fee == 100
        assert client.calls_recent_fees == [(_FAKE_PAYOUT_WALLET, 7)]

    @pytest.mark.asyncio
    async def test_ton_nano_unsorted_input_gets_sorted(self) -> None:
        # Тот же набор, перетасован.
        client = FakeTonRpcClient()
        client.set_recent_fees(
            address=_FAKE_PAYOUT_WALLET,
            fees=_fees_at([100, 30, 70, 20, 50, 10, 60, 90, 40, 80]),
        )
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=500_000_000,
        )

        assert fee == 100

    @pytest.mark.asyncio
    async def test_ton_nano_empty_history_returns_fallback(self) -> None:
        client = FakeTonRpcClient()
        estimator = TonRpcFeeEstimator(
            client=client,
            settings=_make_settings(fallback_fee_buffer_ton_nano=12_345),
        )

        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=1,
        )

        assert fee == 12_345

    @pytest.mark.asyncio
    async def test_ton_nano_single_sample_is_p95(self) -> None:
        client = FakeTonRpcClient()
        client.set_recent_fees(
            address=_FAKE_PAYOUT_WALLET,
            fees=_fees_at([7_777_777]),
        )
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=1,
        )

        assert fee == 7_777_777

    @pytest.mark.asyncio
    async def test_ton_nano_empty_payout_wallet_returns_fallback(self) -> None:
        # Конфигурация неполная — fail-soft в fallback.
        client = FakeTonRpcClient()
        estimator = TonRpcFeeEstimator(
            client=client,
            settings=_make_settings(payout_wallet_address=""),
        )

        fee = await estimator.estimate_fee(
            currency=Currency.TON_NANO,
            target_amount_native=1,
        )

        assert fee == 10_000_000
        # Сеть не тревожили.
        assert client.calls_recent_fees == []


class TestTonRpcFeeEstimatorUsdtDecimal:
    @pytest.mark.asyncio
    async def test_usdt_returns_p95_of_jetton_master_history(self) -> None:
        # P95 of [1_000_000..9_000_000 step 1m + 10_000_000]:
        # 20 элементов с большой выборкой, чтобы покрыть формулу
        # ceil(0.95 * N) для N=20.
        values = [100_000 * (i + 1) for i in range(20)]  # 100k..2_000_000
        # nearest-rank: ceil(0.95 * 20) - 1 = ceil(19) - 1 = 19 - 1 = 18
        # sorted_asc[18] = 1_900_000
        client = FakeTonRpcClient()
        client.set_recent_fees(address=_FAKE_USDT_MASTER, fees=_fees_at(values))
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        fee = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=10**9,
        )

        assert fee == 1_900_000
        assert client.calls_recent_fees == [(_FAKE_USDT_MASTER, 7)]

    @pytest.mark.asyncio
    async def test_usdt_empty_history_returns_fallback(self) -> None:
        client = FakeTonRpcClient()
        estimator = TonRpcFeeEstimator(
            client=client,
            settings=_make_settings(fallback_fee_buffer_usdt_decimal=999),
        )

        fee = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=1,
        )

        assert fee == 999

    @pytest.mark.asyncio
    async def test_usdt_filters_negative_fees_out(self) -> None:
        # Подделанная история с одним «битым» отрицательным значением:
        # его в выборку не берём, P95 считается по оставшимся.
        client = FakeTonRpcClient()
        client.set_recent_fees(
            address=_FAKE_USDT_MASTER,
            fees=_fees_at([-1, 100, 200, 300, 400]),
        )
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        fee = await estimator.estimate_fee(
            currency=Currency.USDT_DECIMAL,
            target_amount_native=1,
        )

        # Из [100,200,300,400] N=4: ceil(0.95*4) - 1 = 4 - 1 = 3 ⇒ 400.
        assert fee == 400


class TestTonRpcFeeEstimatorErrors:
    @pytest.mark.asyncio
    async def test_propagates_call_error(self) -> None:
        client = FakeTonRpcClient()
        client.raise_on_recent_fees(
            TonRpcCallError("rpc down", method="recent_fees"),
        )
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        with pytest.raises(TonRpcCallError):
            await estimator.estimate_fee(
                currency=Currency.TON_NANO,
                target_amount_native=1,
            )

    @pytest.mark.asyncio
    async def test_propagates_timeout_error(self) -> None:
        client = FakeTonRpcClient()
        client.raise_timeout_on_recent_fees(timeout_seconds=5.0)
        estimator = TonRpcFeeEstimator(client=client, settings=_make_settings())

        with pytest.raises(TonRpcTimeoutError):
            await estimator.estimate_fee(
                currency=Currency.USDT_DECIMAL,
                target_amount_native=1,
            )


class TestTonRpcFeeEstimatorContract:
    def test_implements_ifee_estimator_protocol(self) -> None:
        estimator = TonRpcFeeEstimator(client=FakeTonRpcClient(), settings=_make_settings())
        _assert_implements_protocol(estimator)

    def test_estimate_fee_is_coroutine(self) -> None:
        estimator = TonRpcFeeEstimator(client=FakeTonRpcClient(), settings=_make_settings())
        assert inspect.iscoroutinefunction(estimator.estimate_fee)
