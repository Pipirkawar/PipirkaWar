"""Unit-тесты `TonRpcSettings` (Спринт 4.1-D, шаг D.5).

Контракт:
* Дефолты — sandbox-friendly (testnet endpoint, testnet jetton-master).
* `endpoint` лишается trailing slash в валидаторе.
* `fee_window_days >= 1`; `request_timeout_seconds > 0`.
* `api_key` — `SecretStr`; в `repr` маскируется.
* Загружается из env с префиксом `TON_RPC_*`.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings


class TestTonRpcSettingsDefaults:
    def test_defaults_are_sandbox_friendly(self) -> None:
        s = TonRpcSettings()
        assert s.is_sandbox is True
        assert s.endpoint.startswith("https://testnet")
        assert s.fee_window_days == 7
        assert s.request_timeout_seconds == 10.0
        assert s.fallback_fee_buffer_ton_nano == 10_000_000
        assert s.fallback_fee_buffer_usdt_decimal == 200_000
        assert s.payout_wallet_address == ""
        assert s.usdt_jetton_master  # непустая дефолтная строка

    def test_api_key_default_is_none(self) -> None:
        s = TonRpcSettings()
        assert s.api_key is None


class TestTonRpcSettingsValidation:
    def test_endpoint_loses_trailing_slash(self) -> None:
        s = TonRpcSettings(endpoint="https://example.com/api/")
        assert s.endpoint == "https://example.com/api"

    def test_endpoint_without_slash_unchanged(self) -> None:
        s = TonRpcSettings(endpoint="https://example.com/api")
        assert s.endpoint == "https://example.com/api"

    def test_request_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TonRpcSettings(request_timeout_seconds=0)
        with pytest.raises(ValidationError):
            TonRpcSettings(request_timeout_seconds=-1)

    def test_fee_window_days_must_be_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            TonRpcSettings(fee_window_days=0)

    def test_fallback_buffers_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            TonRpcSettings(fallback_fee_buffer_ton_nano=-1)
        with pytest.raises(ValidationError):
            TonRpcSettings(fallback_fee_buffer_usdt_decimal=-1)


class TestTonRpcSettingsSecrets:
    def test_api_key_is_secret_str(self) -> None:
        s = TonRpcSettings(api_key=SecretStr("super-secret-toncenter-key"))
        assert s.api_key is not None
        assert isinstance(s.api_key, SecretStr)
        assert s.api_key.get_secret_value() == "super-secret-toncenter-key"
        # `__repr__` маскирует
        assert "super-secret-toncenter-key" not in repr(s.api_key)


class TestTonRpcSettingsFromEnv:
    def test_loads_from_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TON_RPC_ENDPOINT", "https://mainnet.toncenter.com/api/v2/")
        monkeypatch.setenv("TON_RPC_IS_SANDBOX", "false")
        monkeypatch.setenv("TON_RPC_FEE_WINDOW_DAYS", "14")
        monkeypatch.setenv("TON_RPC_REQUEST_TIMEOUT_SECONDS", "30")
        monkeypatch.setenv(
            "TON_RPC_PAYOUT_WALLET_ADDRESS",
            "0:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        )
        s = TonRpcSettings()
        assert s.endpoint == "https://mainnet.toncenter.com/api/v2"
        assert s.is_sandbox is False
        assert s.fee_window_days == 14
        assert s.request_timeout_seconds == 30.0
        assert s.payout_wallet_address.startswith("0:")
