"""Настройки TON Connect 2.0 verify-flow-а (Спринт 4.1-F, шаг F.7).

Pydantic-settings-секция ``BOT_TON_CONNECT_*``. Все значения — из env
(или ``.env`` локально, который в ``.gitignore``).

Этот config — корневая точка composition root-а 4.1-F: по
``verifier_mode`` ``bot/main.py`` решает, какой ``ITonConnectVerifier``
и какой ``INonceStore`` подключить к use-case-ам ``LinkWallet``-flow:

* ``sandbox`` (default) — ``SandboxTonConnectVerifier`` (D.10.c stub)
  + ``InMemoryNonceStore`` (in-process dict, теряется при рестарте).
  Используется в testnet / sandbox-тестах. Backward-compatible default
  на момент 4.1-F-merge-а.
* ``production`` — ``TonConnectProductionVerifier`` (F.5.c, реальный
  Ed25519-verify) + ``SqlAlchemyNonceStore`` (F.6.b, persistent CAS).
  Включается явным env-флагом для mainnet.

Поля:

* ``verifier_mode: Literal["sandbox", "production"]`` —
  переключатель режима (env: ``BOT_TON_CONNECT_VERIFIER_MODE``).
* ``allowed_domains: tuple[str, ...]`` — whitelist хостов dApp-а,
  на которые ``TonConnectProductionVerifier`` принимает proof-ы.
  Env-CSV: ``BOT_TON_CONNECT_ALLOWED_DOMAINS=pipirik.example.com,foo.example.com``.
  В ``sandbox``-режиме поле игнорируется (`SandboxTonConnectVerifier`
  не смотрит на домены).
* ``canonical_domain: str`` — utf8-имя хоста, которое
  ``RequestLinkWalletProof``-use-case возвращает игроку в phase-1
  (попадает в `ton_proof.domain.value` в phase-2). Должно входить в
  ``allowed_domains`` (валидируется ``__init__``-validator-ом).
* ``max_age_seconds: int = 600`` — лимит «давности» подписи. Default
  10 минут = достаточно для wallet-app-а подписать.
* ``clock_skew_seconds: int = 60`` — допуск на будущее (часы клиента).
* ``nonce_ttl_seconds: int = 600`` — TTL server-side nonce-а.
  Применяется и в sandbox-, и в production-режиме.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["TonConnectSettings"]


class TonConnectSettings(BaseSettings):
    """Конфигурация TON Connect 2.0 verify-flow-а (Спринт 4.1-F, F.7)."""

    model_config = SettingsConfigDict(
        env_prefix="BOT_TON_CONNECT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    verifier_mode: Literal["sandbox", "production"] = Field(
        default="sandbox",
        description=(
            "Режим TonConnect-verifier-а: ``sandbox`` (stub + in-memory) "
            "или ``production`` (Ed25519-verify + SqlAlchemyNonceStore). "
            "Default ``sandbox`` для backward-compatibility 4.1-D/E."
        ),
    )
    allowed_domains: tuple[str, ...] = Field(
        default=("pipirik.example.com",),
        description=(
            "Whitelist хостов dApp-а, на которые "
            "TonConnectProductionVerifier принимает proof-ы. CSV в env."
        ),
    )
    canonical_domain: str = Field(
        default="pipirik.example.com",
        description=(
            "Canonical-domain dApp-а — возвращается игроку в phase-1 "
            "RequestLinkWalletProof; попадает в ton_proof.domain.value "
            "в phase-2."
        ),
    )
    max_age_seconds: int = Field(
        default=600,
        gt=0,
        description=(
            "Лимит «давности» подписи в секундах (proof.timestamp >= now "
            "- max_age_seconds). Default 600 (10 минут)."
        ),
    )
    clock_skew_seconds: int = Field(
        default=60,
        ge=0,
        description=("Допуск на расхождение часов клиента в будущее в секундах. Default 60."),
    )
    nonce_ttl_seconds: int = Field(
        default=600,
        gt=0,
        description=(
            "TTL server-issued nonce-а в секундах. Applies к обоим "
            "режимам (sandbox+production). Default 600 (10 минут)."
        ),
    )

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def _parse_csv_domains(cls, raw: object) -> object:
        """Распарсить CSV-строку из env в tuple[str, ...].

        Pydantic-settings отдаёт env-переменные строками; поддерживаем
        и явный tuple/list (`TonConnectSettings(allowed_domains=(...))`),
        и CSV.
        """
        if raw is None:
            return ()
        if isinstance(raw, str):
            if not raw.strip():
                return ()
            return tuple(p.strip() for p in raw.split(",") if p.strip())
        return raw

    def model_post_init(self, _context: object) -> None:
        """Cross-field-validation: ``canonical_domain`` должен входить в whitelist.

        Защищает от рассинхронизации: если canonical_domain не в
        allowed_domains, verify-у-production-а гарантированно отвергнет
        свой собственный proof — fail-loud сразу при старте, а не на
        первом game-flow-е.
        """
        if self.verifier_mode == "production":
            if not self.allowed_domains:
                raise ValueError(
                    "TonConnectSettings: in production mode allowed_domains "
                    "must be non-empty (set BOT_TON_CONNECT_ALLOWED_DOMAINS).",
                )
            if self.canonical_domain not in self.allowed_domains:
                raise ValueError(
                    f"TonConnectSettings: canonical_domain="
                    f"{self.canonical_domain!r} not in allowed_domains="
                    f"{self.allowed_domains!r}; production-verifier would "
                    "reject the very domain it advertises to players.",
                )
