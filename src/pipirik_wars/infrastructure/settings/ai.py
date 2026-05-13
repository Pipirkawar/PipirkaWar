"""Настройки ИИ-генерации (Спринт 4.1-M, задача 4.1.13).

Опциональный фичефлаг `AI_ENABLED` — если `False` (по умолчанию),
бот использует статические JSON-каталоги шаблонов (`JsonOracleTemplateProvider`
и т.п.). Если `True` — переключается на `AiOracleTemplateProvider`/
`AiForestLogTemplateProvider`/`AiDuelLogTemplateProvider`, которые
генерируют шаблоны через LLM-провайдер (OpenAI) с фоллбэком на
статические каталоги при ошибках.

Ключ `AI_API_KEY` хранится в Devin Secrets / env, в код/git/логи
никогда не попадает (`SecretStr`-маска).

ГДД §14.1 «Growth-stage (JSON + ИИ)» — гибридный режим, где LLM
дополняет/заменяет JSON-шаблоны.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AiSettings(BaseSettings):
    """Настройки ИИ-генерации предсказаний/логов.

    - `enabled` (env `AI_ENABLED`) — главный фичефлаг. По умолчанию
      `False`: бот использует статические JSON-каталоги. Переключение
      на `True` активирует `AiOracleTemplateProvider`/etc и запускает
      фоновую периодическую генерацию.
    - `api_key` (env `AI_API_KEY`) — секрет для OpenAI API. Если
      `enabled=True`, но `api_key=None` → bootstrap fail-loud
      (см. `bot/main.py`).
    - `model` — название модели (`gpt-4o-mini` по умолчанию;
      дешёвая + быстрая для генерации коротких текстов).
    - `base_url` — кастомный endpoint (Azure OpenAI или другой
      OpenAI-compatible provider). `None` ⇒ дефолтный
      `https://api.openai.com/v1`.
    - `timeout_seconds` — таймаут одного запроса к LLM. Generation
      попадает в background, поэтому таймаут можно ставить щедро.
    - `refresh_interval_hours` — как часто перегенерировать кэш
      шаблонов. По умолчанию 24 часа (= 1 раз в сутки).
    - `batch_size_oracle` / `batch_size_forest` / `batch_size_duel` —
      сколько шаблонов запрашивать за один LLM-вызов на локаль.
      Дефолты подобраны так, чтобы один запрос ≈ 1-2K токенов
      output (укладывается в `max_tokens=4096` модели).
    """

    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(
        default=False,
        description=(
            "Включить ИИ-генерацию шаблонов. False ⇒ только статические "
            "JSON-каталоги (legacy/MVP-режим)."
        ),
    )
    api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key. None ⇒ `enabled=True` → fail-loud в bootstrap.",
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Имя LLM-модели (OpenAI-compatible).",
    )
    base_url: str | None = Field(
        default=None,
        description="Кастомный endpoint (Azure / other provider). None ⇒ api.openai.com.",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        description="Таймаут одного LLM-запроса (секунды).",
    )
    refresh_interval_hours: float = Field(
        default=24.0,
        ge=0.5,
        le=168.0,
        description="Частота перегенерации кэша (часы). По умолчанию 1 раз в сутки.",
    )
    batch_size_oracle: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Сколько oracle-шаблонов запрашивать за один LLM-вызов на локаль.",
    )
    batch_size_forest: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Сколько forest-log-шаблонов запрашивать за один LLM-вызов.",
    )
    batch_size_duel: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Сколько duel-log-шаблонов запрашивать за один LLM-вызов.",
    )


__all__ = ["AiSettings"]
