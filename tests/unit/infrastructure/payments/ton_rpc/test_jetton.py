"""Unit-тесты `JettonUsdtProvider` (Спринт 4.1-D, шаг D.5).

Покрытие:
* `resolve_wallet` — happy path (jetton-master вернул адрес).
* `resolve_wallet` — `exit_code != 0` → `JettonResolutionError`.
* `resolve_wallet` — пустой стек → `JettonResolutionError`.
* `resolve_wallet` — пустой адрес в стеке → `JettonResolutionError`.
* `resolve_wallet` — пустой `owner_address` → `JettonResolutionError`.
* `build_transfer_payload` — happy path + все валидации входов.
* конструктор отвергает пустой `jetton_master_address`.
"""

from __future__ import annotations

import pytest

from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    JettonResolutionError,
    TonRpcCallError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.jetton import (
    JettonTransferPayload,
    JettonUsdtProvider,
)
from tests.unit.infrastructure.payments.ton_rpc._fakes import FakeTonRpcClient

_FAKE_JETTON_MASTER = "EQAbcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUV"
_FAKE_OWNER = "0:1111111111111111111111111111111111111111111111111111111111111111"
_FAKE_JETTON_WALLET = "0:2222222222222222222222222222222222222222222222222222222222222222"


def _make_provider(client: FakeTonRpcClient | None = None) -> JettonUsdtProvider:
    return JettonUsdtProvider(
        client=client or FakeTonRpcClient(),
        jetton_master_address=_FAKE_JETTON_MASTER,
    )


class TestJettonUsdtProviderConstruction:
    def test_construction_smoke(self) -> None:
        provider = _make_provider()
        assert provider.jetton_master_address == _FAKE_JETTON_MASTER

    def test_empty_master_address_rejected(self) -> None:
        with pytest.raises(ValueError, match="jetton_master_address must be non-empty"):
            JettonUsdtProvider(client=FakeTonRpcClient(), jetton_master_address="")


class TestJettonUsdtProviderResolveWallet:
    @pytest.mark.asyncio
    async def test_happy_path_returns_jetton_wallet(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(_FAKE_JETTON_WALLET,))
        provider = _make_provider(client)

        wallet = await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        assert wallet == _FAKE_JETTON_WALLET
        assert len(client.calls_run_get_method) == 1
        call = client.calls_run_get_method[0]
        assert call.address == _FAKE_JETTON_MASTER
        assert call.method == "get_wallet_address"
        assert call.stack == (_FAKE_OWNER,)

    @pytest.mark.asyncio
    async def test_non_zero_exit_code_raises_jetton_resolution_error(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=255, stack=())
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError) as exc_info:
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        assert exc_info.value.master_address == _FAKE_JETTON_MASTER
        assert exc_info.value.owner_address == _FAKE_OWNER
        assert exc_info.value.method == "get_wallet_address"

    @pytest.mark.asyncio
    async def test_empty_stack_raises_jetton_resolution_error(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=())
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)

    @pytest.mark.asyncio
    async def test_empty_address_in_stack_raises_jetton_resolution_error(self) -> None:
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=("",))
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)

    @pytest.mark.asyncio
    async def test_empty_owner_raises_jetton_resolution_error_without_call(self) -> None:
        client = FakeTonRpcClient()
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError):
            await provider.resolve_wallet(owner_address="")

        # клиента не дёргали (fail-fast)
        assert client.calls_run_get_method == []

    @pytest.mark.asyncio
    async def test_propagates_ton_rpc_call_error(self) -> None:
        client = FakeTonRpcClient()
        client.raise_on_run_get_method(
            TonRpcCallError("network down", method="run_get_method"),
        )
        provider = _make_provider(client)

        with pytest.raises(TonRpcCallError):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)


class TestJettonUsdtProviderBuildTransferPayload:
    def test_happy_path(self) -> None:
        provider = _make_provider()
        payload = provider.build_transfer_payload(
            query_id=42,
            amount_native=1_000_000,
            destination_jetton_wallet=_FAKE_JETTON_WALLET,
            response_destination=_FAKE_OWNER,
            forward_ton_amount=50_000_000,
        )
        assert isinstance(payload, JettonTransferPayload)
        assert payload.op_code == 0x0F8A7EA5
        assert payload.query_id == 42
        assert payload.amount_native == 1_000_000
        assert payload.destination_jetton_wallet == _FAKE_JETTON_WALLET
        assert payload.response_destination == _FAKE_OWNER
        assert payload.forward_ton_amount == 50_000_000

    def test_forward_ton_amount_defaults_to_zero(self) -> None:
        provider = _make_provider()
        payload = provider.build_transfer_payload(
            query_id=1,
            amount_native=10,
            destination_jetton_wallet=_FAKE_JETTON_WALLET,
            response_destination=_FAKE_OWNER,
        )
        assert payload.forward_ton_amount == 0

    @pytest.mark.parametrize(
        ("query_id", "amount", "fwd", "dest", "resp", "match"),
        [
            (-1, 100, 0, _FAKE_JETTON_WALLET, _FAKE_OWNER, "query_id must be"),
            (0, 0, 0, _FAKE_JETTON_WALLET, _FAKE_OWNER, "amount_native must"),
            (0, 100, -1, _FAKE_JETTON_WALLET, _FAKE_OWNER, "forward_ton_amount"),
            (0, 100, 0, "", _FAKE_OWNER, "destination_jetton_wallet"),
            (0, 100, 0, _FAKE_JETTON_WALLET, "", "response_destination"),
        ],
    )
    def test_invalid_arguments_raise_value_error(
        self,
        query_id: int,
        amount: int,
        fwd: int,
        dest: str,
        resp: str,
        match: str,
    ) -> None:
        provider = _make_provider()
        with pytest.raises(ValueError, match=match):
            provider.build_transfer_payload(
                query_id=query_id,
                amount_native=amount,
                destination_jetton_wallet=dest,
                response_destination=resp,
                forward_ton_amount=fwd,
            )
