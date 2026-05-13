"""Configuration for admin web panel (Sprint 4.5-A, extended 4.5-H).

All settings are read from env-vars with ``ADMIN_WEB_`` prefix.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminWebSettings(BaseSettings):
    """Admin web panel configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ADMIN_WEB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", description="Bind host")
    port: int = Field(default=8080, ge=1, le=65535, description="Bind port")

    secret_key: SecretStr = Field(min_length=32, description="Signed-cookie key (>=32 chars)")
    bot_username: str = Field(description="Telegram bot username for Login Widget")
    bot_token: SecretStr = Field(description="Telegram bot token for HMAC verification")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/pipirik",
        description="SQLAlchemy async DB URL",
    )

    allowed_ips: str = Field(
        default="",
        description="CSV of CIDR ranges; empty = deny-all, '*' = allow-all",
    )
    trust_proxy: bool = Field(
        default=False,
        description="Trust X-Forwarded-For header",
    )
    trusted_proxy_cidrs: str = Field(
        default="",
        description=(
            "CSV of CIDR ranges identifying trusted reverse-proxies. "
            "Used to walk X-Forwarded-For chain right-to-left. "
            "Empty = use private-range heuristic."
        ),
    )
    cookie_insecure_dev: bool = Field(
        default=False,
        description="Allow non-HTTPS cookies (dev only)",
    )

    totp_verify_ttl_seconds: int = Field(default=14400, ge=60, description="TOTP session TTL (4h)")
    session_max_age_seconds: int = Field(default=3600, ge=60, description="Cookie max-age (1h)")

    bootstrap_admin_password: str | None = Field(
        default=None,
        description="Bootstrap password for TOTP self-service setup",
    )

    balance_yaml_path: str = Field(
        default="config/balance.yaml",
        description="Path to balance.yaml (absolute or relative to CWD)",
    )

    # --- Sprint 4.5-H: rate-limiting ---
    rate_limit_max_requests: int = Field(
        default=10,
        ge=1,
        description="Max auth requests per window per IP",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Rate-limit sliding window (seconds)",
    )

    # --- Sprint 4.5-H: subdomain / CORS ---
    subdomain: str = Field(
        default="admin.pipirik.example.com",
        description="Subdomain for admin panel deployment",
    )
    cors_allowed_origins: str = Field(
        default="",
        description=(
            "CSV of allowed CORS origins for the admin panel. "
            "Empty = no CORS headers (same-origin only)."
        ),
    )
