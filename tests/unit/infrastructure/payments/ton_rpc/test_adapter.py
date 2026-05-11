"""Unit-тесты `TonRpcAdapter` (Спринт 4.1-D, шаг D.5).

Контракт `ITonPayoutAdapter`:
* `TON_NANO` payout: собирает TON-выплату, шлёт BOC, возвращает
  `PayoutResult(tx_hash, actual_fee_native)`.
* `USDT_DECIMAL` payout: резолвит jetton-wallet через
  `JettonUsdtProvider`, шлёт BOC jetton-transfer-а, возвращает
  `PayoutResult`.
* `STARS` → `UnsupportedPayoutCurrencyError`.
* Невалидные входы (`amount < 1`, пустой recipient) → `ValueError`.
* Пустой `payout_wallet_address` → `ValueError` (fail-closed).
* Сетевые ошибки клиента — пробрасываются.
"""

from __future__ import annotations

import inspect

import pytest

from pipirik_wars.domain.monetization.ports import ITonPayoutAdapter, PayoutResult
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc.adapter import TonRpcAdapter
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    JettonResolutionError,
    TonRpcCallError,
    UnsupportedPayoutCurrencyError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.jetton import JettonUsdtProvider
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from tests.unit.infrastructure.payments.ton_rpc._fakes import FakeTonRpcClient

_FAKE_PAYOUT_WALLET = "0:4444444444444444444444444444444444444444444444444444444444444444"
_FAKE_USDT_MASTER = "EQAusdtmasterzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
_FAKE_RECIPIENT_TON = "0:5555555555555555555555555555555555555555555555555555555555555555"
_FAKE_RECIPIENT_JETTON_WALLET = "0:6666666666666666666666666666666666666666666666666666666666666666"


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


def _make_adapter(
    client: FakeTonRpcClient | None = None,
    settings: TonRpcSettings | None = None,
) -> tuple[TonRpcAdapter, FakeTonRpcClient]:
    real_client = client or FakeTonRpcClient()
    real_settings = settings or _make_settings()
    jetton_provider = JettonUsdtProvider(
        client=real_client,
        jetton_master_address=real_settings.usdt_jetton_master,
    )
    adapter = TonRpcAdapter(
        client=real_client,
        settings=real_settings,
        jetton_provider=jetton_provider,
    )
    return adapter, real_client


def _assert_implements_protocol(adapter: ITonPayoutAdapter) -> None:
    """Структурная проверка протокола: mypy --strict падает, если
    `TonRpcAdapter` не удовлетворяет `ITonPayoutAdapter`."""
    assert adapter is not None


class TestTonRpcAdapterTonPayout:
    @pytest.mark.asyncio
    async def test_ton_payout_happy_path(self) -> None:
        client = FakeTonRpcClient()
        client.queue_send_boc(tx_hash="0xdeadbeef", actual_fee_native=4_200_000)
        adapter, _ = _make_adapter(client)

        result = await adapter.payout(
            currency=Currency.TON_NANO,
            amount_native=500_000_000,
            recipient_address=_FAKE_RECIPIENT_TON,
        )

        assert isinstance(result, PayoutResult)
        assert result.tx_hash == "0xdeadbeef"
        assert result.actual_fee_native == 4_200_000
        # Один call: send_boc — никаких run_get_method для TON-перевода.
        assert len(client.calls_send_boc) == 1
        assert len(client.calls_run_get_method) == 0
        boc = client.calls_send_boc[0].signed_boc_base64
        assert "ton-payout" in boc
        assert _FAKE_RECIPIENT_TON in boc
        assert _FAKE_PAYOUT_WALLET in boc
        assert "amount=500000000" in boc


class TestTonRpcAdapterUsdtPayout:
    @pytest.mark.asyncio
    async def test_usdt_payout_resolves_jetton_wallet_and_sends_boc(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(_FAKE_RECIPIENT_JETTON_WALLET,))
        client.queue_send_boc(tx_hash="0xabcdef", actual_fee_native=100_000)
        adapter, _ = _make_adapter(client)

        result = await adapter.payout(
            currency=Currency.USDT_DECIMAL,
            amount_native=5_000_000,
            recipient_address=_FAKE_RECIPIENT_TON,
        )

        assert result.tx_hash == "0xabcdef"
        assert result.actual_fee_native == 100_000
        # run_get_method вызван против jetton-master с owner=recipient.
        assert len(client.calls_run_get_method) == 1
        call = client.calls_run_get_method[0]
        assert call.address == _FAKE_USDT_MASTER
        assert call.method == "get_wallet_address"
        assert call.stack == (_FAKE_RECIPIENT_TON,)
        # send_boc payload — jetton-transfer с зарезолвленным jetton-wallet-ом.
        assert len(client.calls_send_boc) == 1
        boc = client.calls_send_boc[0].signed_boc_base64
        assert "jetton-transfer" in boc
        assert _FAKE_RECIPIENT_JETTON_WALLET in boc  # destination jetton wallet
        assert _FAKE_PAYOUT_WALLET in boc  # response destination (excess TON)
        assert "amount=5000000" in boc
        assert "fwd_ton=50000000" in boc
        assert "op=0xf8a7ea5" in boc

    @pytest.mark.asyncio
    async def test_usdt_payout_jetton_resolution_failure_propagates(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=255, stack=())
        adapter, _ = _make_adapter(client)

        with pytest.raises(JettonResolutionError):
            await adapter.payout(
                currency=Currency.USDT_DECIMAL,
                amount_native=1_000_000,
                recipient_address=_FAKE_RECIPIENT_TON,
            )
        # send_boc даже не пробовали.
        assert client.calls_send_boc == []


class TestTonRpcAdapterValidation:
    @pytest.mark.asyncio
    async def test_stars_currency_rejected(self) -> None:
        adapter, client = _make_adapter()

        with pytest.raises(UnsupportedPayoutCurrencyError) as exc_info:
            await adapter.payout(
                currency=Currency.STARS,
                amount_native=1,
                recipient_address=_FAKE_RECIPIENT_TON,
            )

        assert exc_info.value.currency == "stars"
        # клиента не дёргали — fail-fast.
        assert client.calls_send_boc == []
        assert client.calls_run_get_method == []

    @pytest.mark.asyncio
    async def test_zero_amount_rejected(self) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError, match="amount_native must be >= 1"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=0,
                recipient_address=_FAKE_RECIPIENT_TON,
            )

    @pytest.mark.asyncio
    async def test_negative_amount_rejected(self) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError, match="amount_native must be >= 1"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=-100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )

    @pytest.mark.asyncio
    async def test_empty_recipient_rejected(self) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError, match="recipient_address must be non-empty"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address="",
            )

    @pytest.mark.asyncio
    async def test_empty_payout_wallet_rejected(self) -> None:
        adapter, _ = _make_adapter(settings=_make_settings(payout_wallet_address=""))
        with pytest.raises(ValueError, match="payout_wallet_address is empty"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )


class TestTonRpcAdapterNetworkErrors:
    @pytest.mark.asyncio
    async def test_send_boc_failure_propagates(self) -> None:
        client = FakeTonRpcClient()
        client.raise_on_send_boc(TonRpcCallError("rpc down", method="sendBoc"))
        adapter, _ = _make_adapter(client)

        with pytest.raises(TonRpcCallError):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )


class TestTonRpcAdapterContract:
    def test_implements_iton_payout_adapter_protocol(self) -> None:
        adapter, _ = _make_adapter()
        _assert_implements_protocol(adapter)

    def test_payout_is_coroutine(self) -> None:
        adapter, _ = _make_adapter()
        assert inspect.iscoroutinefunction(adapter.payout)
