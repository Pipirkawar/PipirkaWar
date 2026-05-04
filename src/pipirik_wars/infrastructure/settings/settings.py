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
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)
