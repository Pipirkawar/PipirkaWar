"""Настройки HMAC-верификатора TG Stars invoice-payload (Спринт 4.1-D, шаг D.8.b).

Pydantic-settings-секция `TG_STARS_*`. Все значения — из env (или
`.env` локально, который в `.gitignore`). Главное поле — `secret`,
HMAC-ключ для подписи `invoice_payload`-а перед `bot.send_invoice(...)`
и для верификации в `successful_payment`-handler-е (4.1-A handler
выводится в продакшн на шаге D.8.c).

Композиционный root (`bot/main.py`, шаг D.10.c) делает
`TgStarsSettings()` и пробрасывает в `HmacTgStarsPayloadVerifier`.
До D.10 этот класс в проде не используется.

Секрет (`secret`) хранится как `SecretStr` — `__repr__` маскирует
значение, в логи не уходит.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["TgStarsSettings"]


_PAYLOAD_VERSION_DEFAULT = "v1"

# Telegram Bot API лимит для `Invoice.payload` — 128 байт.
_TELEGRAM_INVOICE_PAYLOAD_MAX_BYTES = 128


class TgStarsSettings(BaseSettings):
    """Конфигурация HMAC-верификации Telegram Stars `invoice_payload` (4.1-D, D.8.b).

    Поля:

    * ``secret`` — обязательный `SecretStr`, HMAC-SHA256-ключ.
      Должен быть высокоэнтропийным (>= 32 байта). В env передаётся
      как `TG_STARS_SECRET=<value>`. Никаких дефолтов — fail-closed,
      если env не подключён.
    * ``payload_version`` — версия формата payload-а (`v1`). Меняется
      только при breaking-change-е в payload-формате; верификатор
      отказывает в верификации payload-ов другой версии.
    * ``max_payload_bytes`` — верхняя граница длины raw_payload-а.
      По умолчанию 128 (лимит Telegram). Защищает HMAC от
      DoS-через-длинный-payload (даже не разбираем, если > limit).
    """

    model_config = SettingsConfigDict(
        env_prefix="TG_STARS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret: SecretStr = Field(
        ...,
        description=(
            "Обязательный HMAC-SHA256-ключ для подписи и верификации "
            "Telegram Stars `invoice_payload`-а. Минимум 32 байта энтропии. "
            "Хранится как `SecretStr` — в логи не уходит."
        ),
    )
    payload_version: str = Field(
        default=_PAYLOAD_VERSION_DEFAULT,
        description=(
            "Версия формата payload-а (`v1`). Меняется только при breaking-"
            "change-е сериализации. Верификатор отвергает payload-ы другой "
            "версии."
        ),
    )
    max_payload_bytes: int = Field(
        default=_TELEGRAM_INVOICE_PAYLOAD_MAX_BYTES,
        ge=1,
        le=_TELEGRAM_INVOICE_PAYLOAD_MAX_BYTES,
        description=("Верхняя граница длины raw_payload (≤ 128 — лимит Telegram)."),
    )

    @field_validator("secret")
    @classmethod
    def _secret_is_non_empty(cls, value: SecretStr) -> SecretStr:
        # `SecretStr("")` пройдёт без `field_validator`-а — pydantic
        # не считает пустую строку «отсутствующей». Явно режем пустой
        # секрет, чтобы fail-closed-семантика не зависела от env-парсинга.
        if not value.get_secret_value():
            raise ValueError("TgStarsSettings.secret must be non-empty")
        return value

    @field_validator("payload_version")
    @classmethod
    def _payload_version_is_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("TgStarsSettings.payload_version must be non-empty")
        return value
