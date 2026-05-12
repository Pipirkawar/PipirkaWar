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

import base64

import pytest

from pipirik_wars.infrastructure.payments.ton_rpc.boc import (
    CellBuilder,
    serialize_boc,
)
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


def _encode_addr_boc_b64(workchain: int, account_hash: bytes) -> str:
    """Сериализовать MsgAddressInt-cell как TON Center: base64-encoded BoC.

    Имитирует ответ TON Center на `runGetMethod("get_wallet_address", ...)`
    после flatten-инга `http_client._stack_entry_to_str`: возвращается
    `{"bytes": "<base64-BoC>"}` → base64-стрингу.
    """
    builder = CellBuilder()
    builder.store_address(workchain=workchain, account_hash=account_hash)
    cell = builder.end_cell()
    return base64.b64encode(serialize_boc(cell)).decode("ascii")


class TestJettonUsdtProviderResolveWalletDecodesBoc:
    """Спринт 4.1-E / E.2 — `resolve_wallet` парсит slice-base64-cell от TON Center.

    До E.2 `JettonUsdtProvider.resolve_wallet` возвращал `stack[0]` напрямую.
    Это работало с `FakeTonRpcClient`-стэбом (он клал готовый адрес), но
    в production TON Center отдаёт `["slice", {"bytes": "<base64-BoC>"}]`,
    который `http_client._stack_entry_to_str` flatten-ит в base64-стрингу.
    E.2 добавляет реальный BoC-decode + парсинг `MsgAddressInt addr_std$10`.
    """

    @pytest.mark.asyncio
    async def test_decodes_base64_boc_to_raw_address_basechain(self) -> None:
        account_hash = bytes.fromhex("ab" * 32)
        boc_b64 = _encode_addr_boc_b64(workchain=0, account_hash=account_hash)
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(boc_b64,))
        provider = _make_provider(client)

        wallet = await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        assert wallet == f"0:{'ab' * 32}"

    @pytest.mark.asyncio
    async def test_decodes_base64_boc_to_raw_address_masterchain(self) -> None:
        account_hash = bytes.fromhex("12" * 32)
        boc_b64 = _encode_addr_boc_b64(workchain=-1, account_hash=account_hash)
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(boc_b64,))
        provider = _make_provider(client)

        wallet = await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        assert wallet == f"-1:{'12' * 32}"

    @pytest.mark.asyncio
    async def test_decodes_base64url_no_padding_variant(self) -> None:
        """TON Center может вернуть base64url без `=`-padding-а."""
        account_hash = bytes.fromhex("cd" * 32)
        boc_b64 = _encode_addr_boc_b64(workchain=0, account_hash=account_hash)
        boc_b64url = boc_b64.replace("+", "-").replace("/", "_").rstrip("=")
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(boc_b64url,))
        provider = _make_provider(client)

        wallet = await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        assert wallet == f"0:{'cd' * 32}"

    @pytest.mark.asyncio
    async def test_passes_through_already_parsed_raw_address(self) -> None:
        """Backward-compat для FakeTonRpcClient-стэба: raw `wc:hex` принимаем."""
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(_FAKE_JETTON_WALLET,))
        provider = _make_provider(client)

        wallet = await provider.resolve_wallet(owner_address=_FAKE_OWNER)

        # parse_address + format_raw_address normalises to raw with lower-case hex.
        assert wallet == _FAKE_JETTON_WALLET

    @pytest.mark.asyncio
    async def test_invalid_base64_raises_jetton_resolution_error(self) -> None:
        client = FakeTonRpcClient()
        # Что-то non-address и non-base64 (содержит спецсимволы вне alphabet-а).
        client.queue_run_get_method(exit_code=0, stack=("!!! not base64 !!!",))
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError, match="non-base64-BoC"):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)

    @pytest.mark.asyncio
    async def test_valid_base64_but_not_boc_magic_raises(self) -> None:
        # Base64 валиден, но содержит мусор без BoC-magic-а.
        garbage_b64 = base64.b64encode(b"\x00\x01\x02\x03" * 8).decode("ascii")
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(garbage_b64,))
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError, match="does not decode to MsgAddressInt"):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)

    @pytest.mark.asyncio
    async def test_boc_without_addr_tag_raises(self) -> None:
        # Cell с менее чем 267 битами → parse_msgaddress_int_from_cell даст ValueError.
        builder = CellBuilder()
        builder.store_uint(0x42, 8)  # просто 8 бит, не addr_std
        cell = builder.end_cell()
        boc_b64 = base64.b64encode(serialize_boc(cell)).decode("ascii")
        client = FakeTonRpcClient()
        client.queue_run_get_method(exit_code=0, stack=(boc_b64,))
        provider = _make_provider(client)

        with pytest.raises(JettonResolutionError, match="MsgAddressInt"):
            await provider.resolve_wallet(owner_address=_FAKE_OWNER)
