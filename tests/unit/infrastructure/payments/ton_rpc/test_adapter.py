"""Unit-тесты `TonRpcAdapter` (Спринт 4.1-D, шаги D.5 + D.10.b-3).

Контракт `ITonPayoutAdapter`:
* `TON_NANO` payout: фетчит seqno, собирает TEP-67/wallet-v3R2
  external-message в BoC + Ed25519-signature, шлёт BoC, возвращает
  `PayoutResult(tx_hash, actual_fee_native)`.
* `USDT_DECIMAL` payout: резолвит jetton-wallet через `JettonUsdtProvider`,
  фетчит seqno, собирает TEP-74-jetton-transfer-body, оборачивает в
  TEP-67/wallet-v3R2 external-message + Ed25519-signature, шлёт BoC.
* `STARS` → `UnsupportedPayoutCurrencyError` (fail-fast, без RPC).
* Невалидные входы (`amount < 1`, пустой recipient) → `ValueError`.
* Пустой `payout_wallet_address` → `ValueError` (fail-closed).
* Сетевые ошибки клиента — пробрасываются.

Тесты D.10.b-3 не проверяют конкретное содержимое BoC-байт (это делает
`test_adapter_boc.py` — golden-vectors); здесь — поведенческие тесты:
порядок RPC-вызовов, валидация input, error-propagation, идемпотент-
ность query_id (blake2b от полной payout-tuple).
"""

from __future__ import annotations

import base64
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
from tests.unit.infrastructure.payments.ton_rpc._fakes import (
    FakeTonMessageSigner,
    FakeTonRpcClient,
)

_TON_BOC_MAGIC_HEX = "b5ee9c72"
_FAKE_PAYOUT_WALLET = "0:4444444444444444444444444444444444444444444444444444444444444444"
# `_FAKE_USDT_MASTER` — friendly base64url-form, валидируется только
# `JettonUsdtProvider` (он не парсит адрес — просто кладёт в RPC-payload),
# поэтому подойдёт любой 48-char base64url-string.
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
        "wallet_subwallet_id": 698_983_191,
    }
    defaults.update(overrides)
    return TonRpcSettings(**defaults)  # type: ignore[arg-type]


def _make_adapter(
    client: FakeTonRpcClient | None = None,
    settings: TonRpcSettings | None = None,
    *,
    signer: FakeTonMessageSigner | None = None,
    fixed_now: float | None = None,
) -> tuple[TonRpcAdapter, FakeTonRpcClient]:
    real_client = client or FakeTonRpcClient()
    real_settings = settings or _make_settings()
    real_signer = signer or FakeTonMessageSigner()
    jetton_provider = JettonUsdtProvider(
        client=real_client,
        jetton_master_address=real_settings.usdt_jetton_master,
    )
    clock = (lambda: fixed_now) if fixed_now is not None else None
    adapter = TonRpcAdapter(
        client=real_client,
        settings=real_settings,
        jetton_provider=jetton_provider,
        signer=real_signer,
        clock=clock,
    )
    return adapter, real_client


def _assert_implements_protocol(adapter: ITonPayoutAdapter) -> None:
    """Структурная проверка протокола: mypy --strict падает, если
    `TonRpcAdapter` не удовлетворяет `ITonPayoutAdapter`."""
    assert adapter is not None


def _assert_is_valid_boc_base64(boc_b64: str) -> bytes:
    """Декодирует base64 → проверяет TON BoC magic → возвращает raw bytes."""
    raw = base64.b64decode(boc_b64)
    assert raw[:4].hex() == _TON_BOC_MAGIC_HEX, (
        f"BoC must start with magic {_TON_BOC_MAGIC_HEX}; got {raw[:4].hex()}"
    )
    return raw


class TestTonRpcAdapterTonPayout:
    @pytest.mark.asyncio
    async def test_ton_payout_happy_path(self) -> None:
        client = FakeTonRpcClient()
        # 1) seqno fetch returns 42.
        client.queue_run_get_method(exit_code=0, stack=("42",))
        # 2) send_boc returns tx-hash + fee.
        client.queue_send_boc(tx_hash="0xdeadbeef", actual_fee_native=4_200_000)
        adapter, _ = _make_adapter(client, fixed_now=1_700_000_000.0)

        result = await adapter.payout(
            currency=Currency.TON_NANO,
            amount_native=500_000_000,
            recipient_address=_FAKE_RECIPIENT_TON,
        )

        assert isinstance(result, PayoutResult)
        assert result.tx_hash == "0xdeadbeef"
        assert result.actual_fee_native == 4_200_000
        # 1 seqno-вызов, 0 jetton-resolution, 1 send_boc.
        assert len(client.calls_run_get_method) == 1
        seqno_call = client.calls_run_get_method[0]
        assert seqno_call.address == _FAKE_PAYOUT_WALLET
        assert seqno_call.method == "seqno"
        assert seqno_call.stack == ()
        assert len(client.calls_send_boc) == 1
        boc = client.calls_send_boc[0].signed_boc_base64
        _assert_is_valid_boc_base64(boc)

    @pytest.mark.asyncio
    async def test_ton_payout_propagates_seqno_failure(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=255, stack=())
        adapter, _ = _make_adapter(client)
        with pytest.raises(TonRpcCallError, match="seqno"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )
        # send_boc даже не пробовали.
        assert client.calls_send_boc == []

    @pytest.mark.asyncio
    async def test_ton_payout_propagates_empty_seqno_stack(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=())
        adapter, _ = _make_adapter(client)
        with pytest.raises(TonRpcCallError, match="empty stack"):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )


class TestTonRpcAdapterUsdtPayout:
    @pytest.mark.asyncio
    async def test_usdt_payout_resolves_jetton_wallet_and_sends_boc(self) -> None:
        client = FakeTonRpcClient()
        # 1) jetton-wallet resolution.
        client.queue_run_get_method(exit_code=0, stack=(_FAKE_RECIPIENT_JETTON_WALLET,))
        # 2) seqno fetch.
        client.queue_run_get_method(exit_code=0, stack=("7",))
        # 3) send_boc.
        client.queue_send_boc(tx_hash="0xabcdef", actual_fee_native=100_000)
        adapter, _ = _make_adapter(client, fixed_now=1_700_000_000.0)

        result = await adapter.payout(
            currency=Currency.USDT_DECIMAL,
            amount_native=5_000_000,
            recipient_address=_FAKE_RECIPIENT_TON,
        )

        assert result.tx_hash == "0xabcdef"
        assert result.actual_fee_native == 100_000
        # Сначала jetton-master, потом payout-wallet (seqno).
        assert len(client.calls_run_get_method) == 2
        call0, call1 = client.calls_run_get_method
        assert call0.address == _FAKE_USDT_MASTER
        assert call0.method == "get_wallet_address"
        assert call0.stack == (_FAKE_RECIPIENT_TON,)
        assert call1.address == _FAKE_PAYOUT_WALLET
        assert call1.method == "seqno"
        assert call1.stack == ()
        # send_boc — валидный TON BoC base64.
        assert len(client.calls_send_boc) == 1
        boc = client.calls_send_boc[0].signed_boc_base64
        _assert_is_valid_boc_base64(boc)

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
        # send_boc даже не пробовали; seqno тоже не пытались.
        assert client.calls_send_boc == []
        assert len(client.calls_run_get_method) == 1


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
        # Клиента не дёргали — fail-fast.
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
        client.queue_run_get_method(exit_code=0, stack=("0",))
        client.raise_on_send_boc(TonRpcCallError("rpc down", method="sendBoc"))
        adapter, _ = _make_adapter(client)

        with pytest.raises(TonRpcCallError):
            await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=100,
                recipient_address=_FAKE_RECIPIENT_TON,
            )


class TestTonRpcAdapterQueryIdDerivation:
    """`_derive_query_id` через blake2b — стабилен и детерминирован."""

    def test_query_id_is_deterministic(self) -> None:
        q1 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=12345,
        )
        q2 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=12345,
        )
        assert q1 == q2

    def test_query_id_changes_with_currency(self) -> None:
        q1 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=100,
        )
        q2 = TonRpcAdapter._derive_query_id(
            currency=Currency.USDT_DECIMAL,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=100,
        )
        assert q1 != q2

    def test_query_id_changes_with_recipient(self) -> None:
        q1 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=100,
        )
        q2 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_JETTON_WALLET,
            amount_native=100,
        )
        assert q1 != q2

    def test_query_id_changes_with_amount(self) -> None:
        q1 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=100,
        )
        q2 = TonRpcAdapter._derive_query_id(
            currency=Currency.TON_NANO,
            recipient_address=_FAKE_RECIPIENT_TON,
            amount_native=101,
        )
        assert q1 != q2

    def test_query_id_fits_in_64_bits(self) -> None:
        for amount in (1, 1_000, 1_000_000_000, 2**62):
            q = TonRpcAdapter._derive_query_id(
                currency=Currency.TON_NANO,
                recipient_address=_FAKE_RECIPIENT_TON,
                amount_native=amount,
            )
            assert 0 <= q < (1 << 64)


class TestTonRpcAdapterContract:
    def test_implements_iton_payout_adapter_protocol(self) -> None:
        adapter, _ = _make_adapter()
        _assert_implements_protocol(adapter)

    def test_payout_is_coroutine(self) -> None:
        adapter, _ = _make_adapter()
        assert inspect.iscoroutinefunction(adapter.payout)
