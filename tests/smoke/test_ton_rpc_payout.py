"""Smoke-тесты production TON-RPC payout-стека (Спринт 4.1-D, шаг D.10.d).

Цель — собрать **полную production-цепочку**, как в
`bot/main.py::build_container(...)`, и прогнать её через
`httpx.MockTransport`, чтобы убедиться, что:

* `TonRpcHttpClient` шлёт корректно сформированные запросы к
  TON Center API (`/runGetMethod`, `/sendBoc`, `/getTransactions`);
* `JettonUsdtProvider` использует `get_wallet_address`-метод;
* `Ed25519MessageSigner` подписывает корректно (BoC выходит
  с TON-magic `b5ee9c72`);
* `TonRpcAdapter._fetch_seqno` + `_build_signed_external_message_boc`
  + `client.send_boc` склеиваются в правильную последовательность
  HTTP-вызовов;
* Failure-режимы (jetton-resolve `exit_code != 0`) выкидывают правильные
  доменные ошибки (`JettonResolutionError`).

В отличие от `tests/unit/infrastructure/payments/ton_rpc/*` — здесь
**нет** `FakeTonRpcClient`-а: HTTP-транспорт mocked-ится строго на
уровне `httpx.MockTransport`, как это произойдёт в проде с реальной
TON-нодой.

Marker `smoke` (`@pytest.mark.smoke`) — позволяет выбрать только
smoke-тесты через `pytest -m smoke tests/smoke/` или `make smoke`.
По умолчанию они идут в общий `pytest`-прогон (быстрые).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from pipirik_wars.domain.monetization.ports import PayoutResult
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc import (
    Ed25519MessageSigner,
    JettonResolutionError,
    JettonUsdtProvider,
    TonRpcAdapter,
    TonRpcCallError,
    TonRpcHttpClient,
    TonRpcSettings,
)

_TONCENTER_ENDPOINT = "https://testnet.toncenter.com/api/v2"
# 32-байтовый Ed25519-seed для smoke-теста.  Не «0»*32 — placeholder из
# `TonRpcSettings` дает валидный, но slightly degenerate-pubkey
# (известная особенность Ed25519 при all-zero seed); здесь используем
# фиксированный детерминированный seed для воспроизводимости smoke-а.
_SMOKE_SIGNING_SEED_HEX = "11" * 32
_SMOKE_PAYOUT_WALLET = "0:" + "ab" * 32
_SMOKE_USDT_MASTER = "EQDLvsZol3juZyOAVG8tWsJntOOJEILMru0pkG9LNWZ_smoke"
_SMOKE_RECIPIENT_TON = "0:" + "cd" * 32
_SMOKE_RECIPIENT_JETTON_WALLET = "0:" + "ef" * 32

_TON_BOC_MAGIC = "b5ee9c72"


def _make_settings(**overrides: object) -> TonRpcSettings:
    """Сконструировать `TonRpcSettings` без env-loading.

    Эмулируем D.10.c-сборку: `is_sandbox=True`, реалистичные
    fee-fallback-ы, фиксированный hot-wallet + signing-seed.
    """
    defaults: dict[str, object] = {
        "endpoint": _TONCENTER_ENDPOINT,
        "api_key": None,
        "is_sandbox": True,
        "usdt_jetton_master": _SMOKE_USDT_MASTER,
        "payout_wallet_address": _SMOKE_PAYOUT_WALLET,
        "request_timeout_seconds": 10.0,
        "fee_window_days": 7,
        "fallback_fee_buffer_ton_nano": 10_000_000,
        "fallback_fee_buffer_usdt_decimal": 200_000,
        "wallet_subwallet_id": 698_983_191,
        "payout_wallet_signing_key_seed": SecretStr(_SMOKE_SIGNING_SEED_HEX),
    }
    defaults.update(overrides)
    return TonRpcSettings.model_validate(defaults)


def _build_full_stack(
    *,
    handler: Callable[[httpx.Request], httpx.Response],
    settings: TonRpcSettings | None = None,
) -> tuple[TonRpcAdapter, TonRpcHttpClient]:
    """Собрать production-цепочку поверх `httpx.MockTransport`.

    Эмулирует `bot/main.py::build_container(...)` D.10.c — единственное
    отличие: `httpx.AsyncClient` инжектится с `MockTransport` вместо
    реального HTTP-пула.
    """
    s = settings if settings is not None else _make_settings()
    transport = httpx.MockTransport(handler)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if s.api_key is not None:
        headers["X-API-Key"] = s.api_key.get_secret_value()
    http_client = httpx.AsyncClient(transport=transport, headers=headers)
    rpc_client = TonRpcHttpClient(settings=s, http_client=http_client)
    signer = Ed25519MessageSigner(
        signing_key_seed=bytes.fromhex(s.payout_wallet_signing_key_seed.get_secret_value()),
    )
    jetton_provider = JettonUsdtProvider(
        client=rpc_client,
        jetton_master_address=s.usdt_jetton_master,
    )
    adapter = TonRpcAdapter(
        client=rpc_client,
        settings=s,
        jetton_provider=jetton_provider,
        signer=signer,
        # Детерминированный clock для воспроизводимости BoC-output-а
        # (valid_until зашит в external message).
        clock=lambda: 1_700_000_000.0,
    )
    return adapter, rpc_client


def _is_valid_boc(boc_b64: str) -> bool:
    """Validate base64-encoded TON BoC начинается с magic `b5ee9c72`."""
    try:
        raw = base64.b64decode(boc_b64)
    except (ValueError, TypeError):
        return False
    return raw[:4].hex() == _TON_BOC_MAGIC


@pytest.mark.smoke
class TestTonPayoutFullStack:
    """TON_NANO payout: seqno fetch → sign → send_boc."""

    @pytest.mark.asyncio
    async def test_ton_payout_success(self) -> None:
        """Полная цепочка TON-payout через mocked toncenter v2.

        Шаги:
        1. `POST /runGetMethod {method: "seqno", address: <payout_wallet>}`
           → `{"ok": true, "result": {"exit_code": 0, "stack": [["num", "42"]]}}`.
        2. `POST /sendBoc {boc: <base64>}`
           → `{"ok": true, "result": {"@type": "ok"}}`.

        Adapter возвращает `PayoutResult(tx_hash=sha256(boc), actual_fee_native=0)`.
        """
        recorded: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            url_path = request.url.path
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            recorded.append({"path": url_path, "body": body})
            if url_path.endswith("/runGetMethod"):
                # toncenter seqno-ответ: stack=[["num", "<decimal>"]];
                # _stack_entry_to_str преобразует в "42".
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "result": {"exit_code": 0, "stack": [["num", "42"]]},
                    },
                )
            if url_path.endswith("/sendBoc"):
                return httpx.Response(
                    200,
                    json={"ok": True, "result": {"@type": "ok"}},
                )
            return httpx.Response(404, json={"ok": False, "error": f"unknown {url_path}"})

        adapter, rpc_client = _build_full_stack(handler=handler)
        try:
            result = await adapter.payout(
                currency=Currency.TON_NANO,
                amount_native=500_000_000,
                recipient_address=_SMOKE_RECIPIENT_TON,
            )
        finally:
            await rpc_client.aclose()

        # 1) Returned shape.
        assert isinstance(result, PayoutResult)
        assert isinstance(result.tx_hash, str)
        assert len(result.tx_hash) == 64  # sha256 hex.
        assert result.actual_fee_native == 0

        # 2) HTTP-вызовы в нужном порядке: seqno → sendBoc.
        assert len(recorded) == 2
        assert recorded[0]["path"].endswith("/runGetMethod")
        assert recorded[0]["body"] == {
            "address": _SMOKE_PAYOUT_WALLET,
            "method": "seqno",
            "stack": [],
        }
        assert recorded[1]["path"].endswith("/sendBoc")
        sent_boc = recorded[1]["body"]["boc"]
        assert _is_valid_boc(sent_boc)

    @pytest.mark.asyncio
    async def test_ton_payout_propagates_send_boc_failure(self) -> None:
        """Сетевая ошибка `/sendBoc` пробрасывается из адаптера."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/runGetMethod"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "result": {"exit_code": 0, "stack": [["num", "1"]]},
                    },
                )
            return httpx.Response(
                200,
                json={"ok": False, "error": "invalid boc"},
            )

        adapter, rpc_client = _build_full_stack(handler=handler)
        try:
            with pytest.raises(TonRpcCallError, match="invalid boc"):
                await adapter.payout(
                    currency=Currency.TON_NANO,
                    amount_native=1_000_000,
                    recipient_address=_SMOKE_RECIPIENT_TON,
                )
        finally:
            await rpc_client.aclose()


@pytest.mark.smoke
class TestUsdtPayoutFullStack:
    """USDT_DECIMAL payout: get_wallet_address → seqno → send_boc."""

    @pytest.mark.asyncio
    async def test_usdt_payout_success(self) -> None:
        """Полная цепочка USDT-payout через mocked toncenter v2.

        Шаги:
        1. `POST /runGetMethod {method: "get_wallet_address", address: <jetton_master>, stack: [<recipient>]}`
           → `{"ok": true, "result": {"exit_code": 0, "stack": [["slice", <jetton_wallet>]]}}`.
        2. `POST /runGetMethod {method: "seqno", address: <payout_wallet>}`
           → `{"ok": true, "result": {"exit_code": 0, "stack": [["num", "7"]]}}`.
        3. `POST /sendBoc {boc: <base64>}`
           → `{"ok": true, "result": {"@type": "ok"}}`.

        Adapter возвращает `PayoutResult(tx_hash, actual_fee_native=0)`.
        """
        recorded: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            url_path = request.url.path
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            recorded.append({"path": url_path, "body": body})
            if url_path.endswith("/runGetMethod"):
                # Различаем seqno (адрес = payout_wallet) vs get_wallet_address.
                if body.get("method") == "seqno":
                    return httpx.Response(
                        200,
                        json={
                            "ok": True,
                            "result": {"exit_code": 0, "stack": [["num", "7"]]},
                        },
                    )
                if body.get("method") == "get_wallet_address":
                    return httpx.Response(
                        200,
                        json={
                            "ok": True,
                            "result": {
                                "exit_code": 0,
                                "stack": [
                                    ["slice", _SMOKE_RECIPIENT_JETTON_WALLET],
                                ],
                            },
                        },
                    )
            if url_path.endswith("/sendBoc"):
                return httpx.Response(
                    200,
                    json={"ok": True, "result": {"@type": "ok"}},
                )
            return httpx.Response(404, json={"ok": False, "error": f"unknown {url_path}"})

        adapter, rpc_client = _build_full_stack(handler=handler)
        try:
            result = await adapter.payout(
                currency=Currency.USDT_DECIMAL,
                amount_native=1_500_000,  # 1.5 USDT (6 decimals).
                recipient_address=_SMOKE_RECIPIENT_TON,
            )
        finally:
            await rpc_client.aclose()

        # 1) Returned shape.
        assert isinstance(result, PayoutResult)
        assert isinstance(result.tx_hash, str)
        assert len(result.tx_hash) == 64
        assert result.actual_fee_native == 0

        # 2) Порядок вызовов: jetton-resolve → seqno → sendBoc.
        assert len(recorded) == 3
        assert recorded[0]["path"].endswith("/runGetMethod")
        assert recorded[0]["body"]["method"] == "get_wallet_address"
        assert recorded[0]["body"]["address"] == _SMOKE_USDT_MASTER
        assert recorded[0]["body"]["stack"] == [_SMOKE_RECIPIENT_TON]
        assert recorded[1]["path"].endswith("/runGetMethod")
        assert recorded[1]["body"]["method"] == "seqno"
        assert recorded[1]["body"]["address"] == _SMOKE_PAYOUT_WALLET
        assert recorded[2]["path"].endswith("/sendBoc")
        sent_boc = recorded[2]["body"]["boc"]
        assert _is_valid_boc(sent_boc)


@pytest.mark.smoke
class TestUsdtJettonResolutionFailure:
    """Failure-mode: jetton-master отказал в `get_wallet_address` → `JettonResolutionError`."""

    @pytest.mark.asyncio
    async def test_jetton_master_returns_non_zero_exit_code(self) -> None:
        """`exit_code != 0` от jetton-master-а → `JettonResolutionError`.

        Шаги:
        1. `POST /runGetMethod {method: "get_wallet_address", ...}`
           → `{"ok": true, "result": {"exit_code": 5, "stack": []}}`.

        Adapter ловит `JettonResolutionError` от
        `JettonUsdtProvider.resolve_wallet`; seqno/sendBoc даже не
        пытаются (fail-fast).
        """
        recorded: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            url_path = request.url.path
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            recorded.append({"path": url_path, "body": body})
            if url_path.endswith("/runGetMethod"):
                if body.get("method") == "get_wallet_address":
                    return httpx.Response(
                        200,
                        json={
                            "ok": True,
                            "result": {"exit_code": 5, "stack": []},
                        },
                    )
                if body.get("method") == "seqno":
                    return httpx.Response(
                        200,
                        json={
                            "ok": True,
                            "result": {"exit_code": 0, "stack": [["num", "1"]]},
                        },
                    )
            if url_path.endswith("/sendBoc"):
                return httpx.Response(
                    200,
                    json={"ok": True, "result": {"@type": "ok"}},
                )
            return httpx.Response(404, json={"ok": False, "error": f"unknown {url_path}"})

        adapter, rpc_client = _build_full_stack(handler=handler)
        try:
            with pytest.raises(JettonResolutionError, match="non-zero exit_code=5"):
                await adapter.payout(
                    currency=Currency.USDT_DECIMAL,
                    amount_native=2_000_000,
                    recipient_address=_SMOKE_RECIPIENT_TON,
                )
        finally:
            await rpc_client.aclose()

        # Только jetton-resolve, без seqno / sendBoc.
        assert len(recorded) == 1
        assert recorded[0]["body"]["method"] == "get_wallet_address"
