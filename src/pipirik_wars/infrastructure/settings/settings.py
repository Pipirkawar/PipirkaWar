"""Конфигурация приложения через `pydantic-settings`.

ГДД §0 / `development_plan.md` Спринт 0.2.6: никаких хардкодов и
никаких файлов с секретами в репо. Всё — через env (или через
`.env` локально, который в `.gitignore`).
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Подключение к Postgres (и aiosqlite для тестов)."""

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://postgres:postgres@localhost:5432/pipirik"),
        description="SQLAlchemy async URL: postgresql+asyncpg://... или sqlite+aiosqlite://...",
    )
    echo: bool = Field(default=False, description="Логировать SQL-запросы")
    pool_size: int = Field(default=10, ge=1, le=200)
    max_overflow: int = Field(default=20, ge=0, le=400)


class BotSettings(BaseSettings):
    """Параметры aiogram-бота (Спринт 1.1.C).

    `token` — Telegram Bot API токен, выдаётся `@BotFather`. Хранится в
    Devin Secrets `PIPIRIK_BOT_TOKEN` (`save_scope: org`), в код/git/логи
    никогда не попадает: `SecretStr.__repr__` маскирует значение.

    `default_throttle_per_second` — пропускная способность общего
    rate-limiter-а на одну команду одного пользователя. Дефолт `5`
    выровнен с ГДД §0 / acceptance Спринта 0.2.7 (10 cmd/s — крайний
    антиспам, для штатной работы запас вдвое мягче).

    `default_throttle_capacity` — burst capacity (token-bucket).
    """

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    token: SecretStr = Field(
        default=SecretStr("placeholder:replace-me-with-real-token-from-botfather"),
        description="Telegram Bot API token (@BotFather).",
    )
    default_throttle_per_second: float = Field(default=5.0, gt=0)
    default_throttle_capacity: int = Field(default=10, gt=0)
    referral_rate_limit_capacity: int = Field(
        default=10,
        gt=0,
        description=(
            "Антифрод per-`referrer_tg_id` (Спринт 2.4.F): максимум новых "
            "рефералов в burst-окне. Дефолт `10` — реалистичный «пригласил "
            "друзей за вечер» без блока, но достаточный, чтобы скан-атака "
            "1000 фейк-tg выявилась за час. Отдельный bucket от throttle-а."
        ),
    )
    referral_rate_limit_refill_per_hour: float = Field(
        default=10.0,
        gt=0,
        description=(
            "Скорость долива bucket-а реферального антифрода (новых "
            "рефералов / час). Дефолт `10/h` — лимит ~10 новых в час "
            "после исчерпания burst-окна. ГДД §13.1 «защита от мульти-"
            "аккаунтов»."
        ),
    )
    max_dau: int = Field(
        default=200,
        ge=1,
        description=(
            "Стартовый MAX_DAU (ГДД §18.5: 200 для VPS 1 GB). "
            "Меняется на горячую через `/set_max_dau N`."
        ),
    )


class BootstrapSettings(BaseSettings):
    """Bootstrap-настройки.

    `admin_ids` — список Telegram `tg_id` через запятую. Срабатывает
    один раз при пустой таблице `admins` (см. `BootstrapSuperAdmin`
    use-case). Хранится в Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_TG_ID`,
    в код/git/логи никогда не попадает.
    """

    model_config = SettingsConfigDict(
        env_prefix="BOOTSTRAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    admin_ids: tuple[int, ...] = Field(
        default=(),
        description="Список tg_id через запятую — первые super_admin-ы",
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_csv(cls, raw: object) -> object:
        """Распарсить строку «1234,5678» в кортеж int-ов.

        pydantic-settings отдаёт env-переменные строками; мы поддерживаем
        и явный список (например, при вызове `BootstrapSettings(admin_ids=[...])`),
        и CSV-строку.
        """
        if raw is None or raw == "":
            return ()
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return tuple(int(p) for p in parts)
        return raw


class Settings(BaseSettings):
    """Корень конфигурации.

    Доступ к подсекциям — через атрибуты (`settings.db`, `settings.bootstrap`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="dev", description="dev / staging / prod")
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    bot: BotSettings = Field(default_factory=BotSettings)
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)
