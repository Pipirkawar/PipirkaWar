"""Настройки TON-RPC-адаптеров (Спринт 4.1-D, шаг D.5).

Pydantic-settings-секция `TON_RPC_*`. Все значения — из env (или
`.env` локально, который в `.gitignore`). Дефолты — sandbox-friendly:
`testnet`-endpoint toncenter, тестовый jetton-master USDT (для
sandbox-демо), 1 час timeout, 7-дневное P95-окно. Реальный
`production`-режим конфигурируется явно через env (`TON_RPC_IS_SANDBOX=false`,
`TON_RPC_USDT_JETTON_MASTER=<mainnet-USDT-master>`).

Композиционный root (`bot/main.py`, шаг D.10) делает
`TonRpcSettings()` и пробрасывает в `TonRpcAdapter` / `TonRpcFeeEstimator`
/ `JettonUsdtProvider`. До D.10 эти классы в проде не используются.

Секреты (`api_key`) хранятся как `SecretStr` — `__repr__` маскирует
значение, в логи не уходят.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["TonRpcSettings"]


# Известные публичные testnet jetton-master-ы для sandbox-режима.
# Конкретный адрес — не критичен (это всё равно тестовая сеть), важен
# формат: 48-character user-friendly base64url.
_TESTNET_USDT_JETTON_MASTER_DEFAULT = "kQAiboDEv_qRrcEdrYdwbVLNOXBHwShFbtKGbQVJ2OKxY_Di"

# Endpoint-ы по умолчанию. Реальный mainnet — `https://toncenter.com/api/v2`,
# testnet — `https://testnet.toncenter.com/api/v2`. Дефолт — testnet, чтобы
# случайный `TonRpcSettings()` без env не наехал на mainnet.
_TESTNET_TONCENTER_ENDPOINT_DEFAULT = "https://testnet.toncenter.com/api/v2"


class TonRpcSettings(BaseSettings):
    """Конфигурация TON-RPC-адаптеров (Спринт 4.1-D, шаг D.5).

    Поля:

    * ``endpoint`` — базовый URL TON-RPC-провайдера (toncenter /
      tonapi / native node). Без trailing slash.
    * ``api_key`` — опциональный `SecretStr`-ключ для авторизации
      у провайдера (toncenter-style query-param-ключ). Пустой `None`
      — публичный endpoint без аутентификации (rate-limit более жёсткий).
    * ``is_sandbox`` — `True` для testnet / sandbox; `False` для
      production mainnet. Используется адаптерами для отказа от
      некоторых rev-операций (например, sandbox-mode допускает
      эмуляцию выплаты без реальной публикации BOC-а; D.10 решит,
      нужна ли эта семантика).
    * ``usdt_jetton_master`` — адрес USDT-jetton-master-смарт-контракта.
      На mainnet это `EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs`
      (TON-USDT, TT-проект Tether). На testnet — публичный тестовый
      jetton-master (значение зависит от деплоя; дефолт — пример).
    * ``payout_wallet_address`` — адрес нашего hot-wallet-а, с которого
      адаптер платит призы. Должен быть пополнен до старта Спринта 4.1-D
      (operational concern; secrets-management ключа подписи — на D.10).
    * ``request_timeout_seconds`` — таймаут одного RPC-вызова.
    * ``fee_window_days`` — окно для P95-оценки газа (`>= 1`).
      Дефолт `7` соответствует ГДД §12.6.3.
    * ``fallback_fee_buffer_ton_nano`` / ``fallback_fee_buffer_usdt_decimal``
      — fallback-значения, если `client.recent_fees(...)` вернул пустой
      список (нет истории). Совпадают с константами `InMemoryFeeEstimator`
      (4.1-C), чтобы переход на TonRpc-адаптер не менял баланс.
    """

    model_config = SettingsConfigDict(
        env_prefix="TON_RPC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint: str = Field(
        default=_TESTNET_TONCENTER_ENDPOINT_DEFAULT,
        description="Базовый URL TON-RPC-провайдера, без trailing slash.",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Опциональный API-ключ TON-RPC-провайдера (toncenter-style). "
            "`None` — публичный endpoint."
        ),
    )
    is_sandbox: bool = Field(
        default=True,
        description="`True` — testnet; `False` — mainnet.",
    )
    usdt_jetton_master: str = Field(
        default=_TESTNET_USDT_JETTON_MASTER_DEFAULT,
        description=(
            "Адрес USDT-jetton-master-смарт-контракта (mainnet или testnet "
            "в зависимости от `is_sandbox`)."
        ),
    )
    payout_wallet_address: str = Field(
        default="",
        description=(
            "Адрес hot-wallet-а, с которого `TonRpcAdapter` платит призы. "
            "Пустая строка ⇒ адаптер откажет на любых вызовах payout (fail-closed)."
        ),
    )
    request_timeout_seconds: float = Field(
        default=10.0,
        gt=0.0,
        description="Таймаут одного RPC-вызова в секундах.",
    )
    fee_window_days: int = Field(
        default=7,
        ge=1,
        description="Окно для P95-оценки газа (>= 1 день).",
    )
    fallback_fee_buffer_ton_nano: int = Field(
        default=10_000_000,
        ge=0,
        description=(
            "Fallback-буфер для TON_NANO при пустой истории. По умолчанию "
            "выровнен с `InMemoryFeeEstimator` (0.01 TON)."
        ),
    )
    fallback_fee_buffer_usdt_decimal: int = Field(
        default=200_000,
        ge=0,
        description=(
            "Fallback-буфер для USDT_DECIMAL при пустой истории. По умолчанию "
            "выровнен с `InMemoryFeeEstimator` (0.2 USDT)."
        ),
    )
    wallet_subwallet_id: int = Field(
        default=698_983_191,
        ge=0,
        description=(
            "`subwallet_id` для wallet-v3R2 external-message-а (TEP-67-wrap). "
            "Default `698983191` — стандартный mainnet basechain wallet_id "
            "(см. wallet-v3R2 reference в @ton/ton). "
            "Production может переопределить через `TON_RPC_WALLET_SUBWALLET_ID`."
        ),
    )
    payout_wallet_signing_key_seed: SecretStr = Field(
        default=SecretStr("0" * 64),
        description=(
            "Hex-кодированный (64 hex-символа = 32 байта) Ed25519-seed "
            "hot-wallet-а. Используется `Ed25519MessageSigner`-ом для "
            "подписи внешних message-ей. Дефолт `0`*32 — placeholder, "
            "подходит только для unit-tests / sandbox; production должен "
            "задать через `TON_RPC_PAYOUT_WALLET_SIGNING_KEY_SEED`. "
            "`SecretStr` маскирует значение в `__repr__`/`logs`."
        ),
    )

    @field_validator("endpoint", mode="after")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Убрать trailing `/` — упрощает конкатенацию путей."""
        return value.rstrip("/")

    @field_validator("payout_wallet_signing_key_seed", mode="after")
    @classmethod
    def _validate_signing_key_seed_hex(cls, value: SecretStr) -> SecretStr:
        """Проверить, что seed — 64 hex-символа (32 байта Ed25519).

        Не декодируем сюда — это делает composition-root при сборке
        `Ed25519MessageSigner`. Здесь только формат: длина 64 + hex.
        """
        raw = value.get_secret_value()
        if len(raw) != 64:
            raise ValueError(
                "TonRpcSettings.payout_wallet_signing_key_seed must be 64 hex chars "
                f"(32 bytes Ed25519 seed), got {len(raw)}",
            )
        try:
            bytes.fromhex(raw)
        except ValueError as exc:
            raise ValueError(
                "TonRpcSettings.payout_wallet_signing_key_seed must be valid hex",
            ) from exc
        return value
