"""Unit-тесты `TonRpcHttpClient` (Спринт 4.1-D, шаг D.10.a).

Все тесты гоняются через `httpx.MockTransport` — без реальной сети,
без `pytest-httpx`/`respx`-зависимостей. На каждый exchange описываем
полный JSON-ответ TON Center-а; на каждую ошибку — соответствующий
HTTP-статус / non-JSON-тело / `ok=false`-конверт.

Покрытие:

* HTTP-конверт: `ok=true` / `ok=false` / 4xx / 5xx / timeout /
  non-JSON.
* `run_get_method`: успех / `exit_code != 0` / нестандартный стек.
* `send_boc`: успех (детерминированный `tx_hash`) / ошибка / timeout.
* `recent_fees`: пустой массив / фильтрация по окну / отбрасывание
  невалидных tx / отрицательные fee-ы / сортировка по `occurred_at`.
* API-key передаётся в `X-API-Key`-header.
* Конструктор по умолчанию создаёт собственный `AsyncClient` и
  закрывает его в `aclose()`; external `AsyncClient` не трогает.
* Структурная проверка: `TonRpcHttpClient` реализует `ITonRpcClient`
  (mypy-Protocol). Это компилирует — `TonRpcAdapter`-фабрика в
  composition root-е (`bot/main.py`, D.10.c) её принимает.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import islice
from typing import Any

import httpx
import pytest

from pipirik_wars.infrastructure.payments.ton_rpc.client import ITonRpcClient
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    TonRpcCallError,
    TonRpcTimeoutError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.http_client import (
    TonRpcHttpClient,
    _derive_tx_hash_from_boc,
    _parse_toncenter_envelope,
    _stack_entry_to_str,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings

_TEST_ENDPOINT = "https://testnet.toncenter.com/api/v2"


def _settings(*, api_key: str | None = None, timeout: float = 5.0) -> TonRpcSettings:
    """Сборка `TonRpcSettings` без чтения env (`_env_file=None`)."""
    return TonRpcSettings.model_validate(
        {
            "endpoint": _TEST_ENDPOINT,
            "api_key": api_key,
            "is_sandbox": True,
            "request_timeout_seconds": timeout,
            "fee_window_days": 7,
            "payout_wallet_address": "EQA-fake-hot-wallet",
        },
    )


def _build_mock_client(
    *,
    handler: Any,
    settings: TonRpcSettings | None = None,
) -> TonRpcHttpClient:
    """Сконструировать `TonRpcHttpClient` поверх `httpx.MockTransport`."""
    s = settings if settings is not None else _settings()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if s.api_key is not None:
        headers["X-API-Key"] = s.api_key.get_secret_value()
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, headers=headers)
    return TonRpcHttpClient(settings=s, http_client=http_client)


# ---------------------------------------------------------------------
# Базовые свойства класса (структура / конструктор / Protocol-conformance).
# ---------------------------------------------------------------------


class TestStructure:
    """Контракт класса: реализует Protocol, аккуратно владеет соединением."""

    def test_satisfies_iton_rpc_client_protocol(self) -> None:
        """`TonRpcHttpClient` — это `ITonRpcClient` (Protocol-структурно)."""

        def _accepts_iton_rpc(client: ITonRpcClient) -> ITonRpcClient:
            return client

        client = _build_mock_client(handler=lambda _: httpx.Response(200))
        # mypy: проверка типа на runtime (помимо compile-time);
        # сам факт того, что `_accepts_iton_rpc(client)` принимается
        # mypy-ом (`make typecheck`), уже доказывает структурную
        # совместимость.
        assert _accepts_iton_rpc(client) is client

    @pytest.mark.asyncio
    async def test_owns_internal_client_and_closes(self) -> None:
        """Без `http_client`-injection класс создаёт свой и закрывает его."""
        settings = _settings()
        client = TonRpcHttpClient(settings=settings)
        assert client._owns_http_client is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_external_client_not_closed(self) -> None:
        """С `http_client`-injection `aclose()` не закрывает внешний клиент."""
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True}))
        async with httpx.AsyncClient(transport=transport) as external:
            client = TonRpcHttpClient(settings=_settings(), http_client=external)
            await client.aclose()
            # `external` всё ещё открыт — `async with` выйдет нормально.
            assert not external.is_closed

    def test_endpoint_normalized_no_trailing_slash(self) -> None:
        """Trailing slash из `endpoint` срезается при конструировании."""
        settings = TonRpcSettings.model_validate(
            {
                "endpoint": _TEST_ENDPOINT + "/",
                "api_key": None,
                "is_sandbox": True,
                "request_timeout_seconds": 5.0,
                "fee_window_days": 7,
                "payout_wallet_address": "EQA",
            },
        )
        client = _build_mock_client(handler=lambda _: httpx.Response(200), settings=settings)
        assert client._endpoint == _TEST_ENDPOINT


# ---------------------------------------------------------------------
# `_parse_toncenter_envelope` / `_stack_entry_to_str` / `_derive_tx_hash_from_boc`
# — пуристические unit-тесты низкоуровневых хелперов.
# ---------------------------------------------------------------------


class TestEnvelopeHelpers:
    """Тесты на парсинг конверта TON Center и сериализацию стека."""

    def test_envelope_unwraps_ok_result(self) -> None:
        result = _parse_toncenter_envelope(
            body={"ok": True, "result": {"exit_code": 0}},
            endpoint="X",
            method="m",
        )
        assert result == {"exit_code": 0}

    def test_envelope_raises_on_ok_false(self) -> None:
        with pytest.raises(TonRpcCallError) as exc:
            _parse_toncenter_envelope(
                body={"ok": False, "error": "rate limit"},
                endpoint="X",
                method="m",
            )
        assert "rate limit" in str(exc.value)
        assert exc.value.endpoint == "X"
        assert exc.value.method == "m"

    def test_envelope_raises_on_non_dict_body(self) -> None:
        with pytest.raises(TonRpcCallError):
            _parse_toncenter_envelope(body=[1, 2, 3], endpoint="X", method="m")  # type: ignore[arg-type]

    def test_envelope_raises_on_non_dict_result(self) -> None:
        with pytest.raises(TonRpcCallError):
            _parse_toncenter_envelope(
                body={"ok": True, "result": "oops"},
                endpoint="X",
                method="m",
            )

    def test_stack_entry_str_value(self) -> None:
        assert _stack_entry_to_str(["num", "0x42"]) == "0x42"

    def test_stack_entry_dict_with_bytes(self) -> None:
        assert _stack_entry_to_str(["cell", {"bytes": "AAEC"}]) == "AAEC"

    def test_stack_entry_unknown_form(self) -> None:
        # На незнакомой форме сериализуем в стабильный JSON.
        out = _stack_entry_to_str({"weird": True})
        assert out == json.dumps({"weird": True}, sort_keys=True, separators=(",", ":"))

    def test_derive_tx_hash_deterministic(self) -> None:
        first = _derive_tx_hash_from_boc("dGVzdC1ib2M=")  # "test-boc"
        second = _derive_tx_hash_from_boc("dGVzdC1ib2M=")
        assert first == second
        assert len(first) == 64  # sha256-hex.

    def test_derive_tx_hash_different_for_different_boc(self) -> None:
        first = _derive_tx_hash_from_boc("dGVzdC1ib2NfQQ==")
        second = _derive_tx_hash_from_boc("dGVzdC1ib2NfQg==")
        assert first != second

    def test_derive_tx_hash_invalid_base64_fallback(self) -> None:
        # Невалидный base64 — fallback на utf-8-байты исходной строки.
        out = _derive_tx_hash_from_boc("!!!invalid-base64@@@")
        assert len(out) == 64


# ---------------------------------------------------------------------
# `run_get_method`
# ---------------------------------------------------------------------


class TestRunGetMethod:
    """`runGetMethod` — happy-path + error-paths."""

    @pytest.mark.asyncio
    async def test_happy_path_parses_exit_code_and_stack(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["json"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "exit_code": 0,
                        "stack": [["cell", {"bytes": "AAEC"}], ["num", "0x10"]],
                    },
                },
            )

        client = _build_mock_client(handler=handler)
        result = await client.run_get_method(
            address="EQA-master",
            method="get_wallet_address",
            stack=["EQA-owner"],
        )
        assert result.exit_code == 0
        assert result.stack == ("AAEC", "0x10")
        assert captured["method"] == "POST"
        assert captured["url"].endswith("/runGetMethod")
        assert captured["json"] == {
            "address": "EQA-master",
            "method": "get_wallet_address",
            "stack": ["EQA-owner"],
        }
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_zero_exit_code_passed_through(self) -> None:
        """Non-zero `exit_code` — это валидный ответ, не RPC-ошибка."""
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": {"exit_code": 7, "stack": []}},
            ),
        )
        result = await client.run_get_method(address="EQA", method="get_x")
        assert result.exit_code == 7
        assert result.stack == ()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_ok_false_raises_call_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(200, json={"ok": False, "error": "broken"}),
        )
        with pytest.raises(TonRpcCallError) as exc:
            await client.run_get_method(address="EQA", method="get_x")
        assert "broken" in str(exc.value)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_http_500_raises_call_error(self) -> None:
        client = _build_mock_client(handler=lambda _: httpx.Response(500, text="boom"))
        with pytest.raises(TonRpcCallError) as exc:
            await client.run_get_method(address="EQA", method="get_x")
        assert "HTTP 500" in str(exc.value)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_json_body_raises_call_error(self) -> None:
        client = _build_mock_client(handler=lambda _: httpx.Response(200, text="<html>fail"))
        with pytest.raises(TonRpcCallError):
            await client.run_get_method(address="EQA", method="get_x")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        client = _build_mock_client(handler=handler)
        with pytest.raises(TonRpcTimeoutError) as exc:
            await client.run_get_method(address="EQA", method="get_x")
        assert exc.value.timeout_seconds == 5.0
        assert exc.value.method == "get_x"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_invalid_exit_code_raises_call_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": {"exit_code": "not-int", "stack": []}},
            ),
        )
        with pytest.raises(TonRpcCallError):
            await client.run_get_method(address="EQA", method="get_x")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_list_stack_raises_call_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": {"exit_code": 0, "stack": "broken"}},
            ),
        )
        with pytest.raises(TonRpcCallError):
            await client.run_get_method(address="EQA", method="get_x")
        await client.aclose()


# ---------------------------------------------------------------------
# `send_boc`
# ---------------------------------------------------------------------


class TestSendBoc:
    @pytest.mark.asyncio
    async def test_happy_path_returns_derived_tx_hash(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["json"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={"ok": True, "result": {"@type": "ok", "hash": "ignored"}},
            )

        client = _build_mock_client(handler=handler)
        result = await client.send_boc(signed_boc_base64="dGVzdC1ib2M=")
        assert captured["url"].endswith("/sendBoc")
        assert captured["json"] == {"boc": "dGVzdC1ib2M="}
        assert result.tx_hash == _derive_tx_hash_from_boc("dGVzdC1ib2M=")
        assert result.actual_fee_native == 0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_ok_false_raises_call_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": False, "error": "invalid boc"},
            ),
        )
        with pytest.raises(TonRpcCallError) as exc:
            await client.send_boc(signed_boc_base64="dGVzdC1ib2M=")
        assert "invalid boc" in str(exc.value)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("connect timed out", request=request)

        client = _build_mock_client(handler=handler)
        with pytest.raises(TonRpcTimeoutError):
            await client.send_boc(signed_boc_base64="dGVzdC1ib2M=")
        await client.aclose()


# ---------------------------------------------------------------------
# `recent_fees`
# ---------------------------------------------------------------------


def _utime_iter(start: datetime, *, step_minutes: int = 60) -> Iterator[int]:
    cur = start
    while True:
        yield int(cur.timestamp())
        cur += timedelta(minutes=step_minutes)


class TestRecentFees:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(200, json={"ok": True, "result": []}),
        )
        fees = await client.recent_fees(address="EQA", days=7)
        assert fees == ()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_parses_and_sorts_in_window(self) -> None:
        now = datetime.now(tz=UTC)
        utimes = list(islice(_utime_iter(now - timedelta(days=3), step_minutes=60), 3))
        result = [
            {"utime": utimes[2], "fee": "30"},
            {"utime": utimes[0], "fee": 10},
            {"utime": utimes[1], "fee": 20},
        ]

        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": result},
            ),
        )
        fees = await client.recent_fees(address="EQA", days=7)
        assert [f.fee_native for f in fees] == [10, 20, 30]
        # Сортировка по occurred_at.
        assert fees[0].occurred_at <= fees[1].occurred_at <= fees[2].occurred_at
        await client.aclose()

    @pytest.mark.asyncio
    async def test_filters_out_old_tx(self) -> None:
        now = datetime.now(tz=UTC)
        too_old_utime = int((now - timedelta(days=30)).timestamp())
        fresh_utime = int((now - timedelta(hours=1)).timestamp())
        result = [
            {"utime": too_old_utime, "fee": 999},
            {"utime": fresh_utime, "fee": 100},
        ]
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": result},
            ),
        )
        fees = await client.recent_fees(address="EQA", days=7)
        assert len(fees) == 1
        assert fees[0].fee_native == 100
        await client.aclose()

    @pytest.mark.asyncio
    async def test_drops_malformed_tx(self) -> None:
        now = datetime.now(tz=UTC)
        fresh_utime = int((now - timedelta(hours=1)).timestamp())
        result = [
            "not-a-dict",
            {"utime": "not-int", "fee": 1},
            {"utime": fresh_utime},  # missing fee
            {"fee": 5},  # missing utime
            {"utime": fresh_utime, "fee": -1},  # negative fee
            {"utime": fresh_utime, "fee": 42},  # valid
        ]
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": result},
            ),
        )
        fees = await client.recent_fees(address="EQA", days=7)
        assert len(fees) == 1
        assert fees[0].fee_native == 42
        await client.aclose()

    @pytest.mark.asyncio
    async def test_invalid_days_raises_value_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(200, json={"ok": True, "result": []}),
        )
        with pytest.raises(ValueError, match="days must be >= 1"):
            await client.recent_fees(address="EQA", days=0)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_list_result_raises_call_error(self) -> None:
        client = _build_mock_client(
            handler=lambda _: httpx.Response(
                200,
                json={"ok": True, "result": {"unexpected": "object"}},
            ),
        )
        with pytest.raises(TonRpcCallError):
            await client.recent_fees(address="EQA", days=7)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_get_uses_address_and_limit_params(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            return httpx.Response(200, json={"ok": True, "result": []})

        client = _build_mock_client(handler=handler)
        await client.recent_fees(address="EQA-hot", days=7)
        assert captured["method"] == "GET"
        assert "address=EQA-hot" in captured["url"]
        assert "limit=256" in captured["url"]
        await client.aclose()


# ---------------------------------------------------------------------
# API-key прокидывается в заголовок.
# ---------------------------------------------------------------------


class TestApiKey:
    @pytest.mark.asyncio
    async def test_api_key_sent_as_x_api_key_header(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["x_api_key"] = request.headers.get("X-API-Key")
            return httpx.Response(200, json={"ok": True, "result": []})

        client = _build_mock_client(
            handler=handler,
            settings=_settings(api_key="secret-key"),
        )
        await client.recent_fees(address="EQA-hot", days=7)
        assert captured["x_api_key"] == "secret-key"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_no_api_key_omits_header(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["x_api_key"] = request.headers.get("X-API-Key")
            return httpx.Response(200, json={"ok": True, "result": []})

        client = _build_mock_client(handler=handler, settings=_settings(api_key=None))
        await client.recent_fees(address="EQA-hot", days=7)
        assert captured["x_api_key"] is None
        await client.aclose()
