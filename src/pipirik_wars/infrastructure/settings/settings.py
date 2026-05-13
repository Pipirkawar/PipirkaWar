"""Конфигурация приложения через `pydantic-settings`.

ГДД §0 / `development_plan.md` Спринт 0.2.6: никаких хардкодов и
никаких файлов с секретами в репо. Всё — через env (или через
`.env` локально, который в `.gitignore`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings
from pipirik_wars.infrastructure.payments.ton_connect.settings import TonConnectSettings
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from pipirik_wars.infrastructure.redis.settings import RedisSettings


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
    activity_lock_backend: Literal["sql", "redis"] = Field(
        default="sql",
        description=(
            "Бэкенд для `IActivityLockRepository` (Спринт 4.1-G, G.4). "
            "`sql` (default) — `SqlAlchemyActivityLockRepository` поверх "
            "таблицы `activity_locks`. `redis` — `RedisActivityLockRepository` "
            "поверх `redis.asyncio.Redis` (требует поднятого Redis-инстанса "
            "по `settings.redis.url`). Переключается env-флагом "
            "`BOT_ACTIVITY_LOCK_BACKEND=redis`."
        ),
    )
    lobby_backend: Literal["sql", "redis"] = Field(
        default="sql",
        description=(
            "Бэкенд для `IGlobalLobbyRepository` (Спринт 4.1-H, H.2). "
            "`sql` (default) — `SqlAlchemyGlobalLobbyRepository` поверх "
            "таблицы `pvp_global_lobby`. `redis` — `RedisGlobalLobbyRepository` "
            "поверх `redis.asyncio.Redis` (LIST + HASH + atomic Lua-скрипты; "
            "требует поднятого Redis-инстанса по `settings.redis.url`). "
            "Переключается env-флагом `BOT_LOBBY_BACKEND=redis`."
        ),
    )
    dau_backend: Literal["sql", "redis"] = Field(
        default="sql",
        description=(
            "Бэкенд для `IDauCounter` (Спринт 4.1-I, I.2). "
            "`sql` (default-name; реально — in-memory `InMemoryDauCounter` "
            "из `infrastructure/dau`; имя `sql` сохранено для единообразия "
            "с `activity_lock_backend`/`lobby_backend`) — счётчик активных "
            "за день живёт в `asyncio`-Lock-нутом `set[int]` и теряется на "
            "рестарте бота (по-прежнему достаточно для MVP DAU=200). "
            "`redis` — `RedisDauCounter` поверх `redis.asyncio.Redis` "
            "(per-day ZSET `dau:{YYYY-MM-DD}` + TTL 48h; pipelined "
            "ZADD+EXPIRE; ZCARD-based `current()`). Переживает рестарт, "
            "lazy-reset на МСК-полночи через смену key-а. Требует поднятого "
            "Redis-инстанса по `settings.redis.url`. Переключается "
            "env-флагом `BOT_DAU_BACKEND=redis`."
        ),
    )


class BootstrapSettings(BaseSettings):
    """Bootstrap-настройки.

    `admin_ids` — список Telegram `tg_id` через запятую. Срабатывает
    один раз при пустой таблице `admins` (см. `BootstrapSuperAdmin`
    use-case). Хранится в Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_TG_ID`,
    в код/git/логи никогда не попадает.

    `admin_password` (Спринт 2.5-D.6, ГДД §18.6.5) — out-of-band
    bootstrap-пароль для команды `/admin_setup_totp`: super-admin
    использует его, чтобы инициализировать свой TOTP-секрет. Хранится
    в Devin Secrets `PIPIRIK_BOOTSTRAP_ADMIN_PASSWORD` (`save_scope: org`),
    в код/git/логи никогда не попадает (`SecretStr` маскирует значение).
    Если переменная не задана — команда `/admin_setup_totp` отказывается
    работать (fail-closed): self-service-выдача нового TOTP-секрета без
    второго фактора недопустима.
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
    admin_password: SecretStr | None = Field(
        default=None,
        description=(
            "Out-of-band bootstrap-пароль для `/admin_setup_totp` "
            "(Спринт 2.5-D.6). `None` ⇒ команда отказывает (fail-closed)."
        ),
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
    # Спринт 4.1-D, шаг D.10.c: настройки TON-RPC-адаптера и
    # HMAC-верификатора Telegram Stars `invoice_payload`. Оба поля —
    # `Optional`, потому что:
    # 1) `TgStarsSettings.secret` — обязательное (без env-var-а
    #    `TG_STARS_SECRET` `TgStarsSettings()` бросает `ValidationError`).
    #    `Settings` не должен ронять весь bootstrap, если этой переменной
    #    нет (unit-тесты собирают `Settings()` без env-context-а).
    # 2) `TonRpcSettings` сам по себе не требует env, но имеет placeholder-
    #    дефолты (`payout_wallet_address=""`, `payout_wallet_signing_key_seed`
    #    = 32 zero-byte) — `build_container` сам разрулит fail-loud
    #    если placeholder-ы используются в проде.
    # `build_container` интерпретирует `None` как «собрать с дефолтами»
    # (или не собрать вообще, если секреты не заданы).
    ton_rpc: TonRpcSettings | None = Field(default=None)
    tg_stars: TgStarsSettings | None = Field(default=None)
    # Спринт 4.1-F (шаг F.7): TON Connect 2.0 verify-flow.
    # Сборка по дефолту всегда получает «backward-compat»-sandbox-default,
    # поэтому (в отличие от ``ton_rpc``/``tg_stars``, требующих секреты)
    # поле не ``Optional``: ``TonConnectSettings()`` без env всегда
    # собирается. ``mode=production`` выбирается явным
    # флагом ``BOT_TON_CONNECT_VERIFIER_MODE=production``.
    ton_connect: TonConnectSettings = Field(default_factory=TonConnectSettings)
    # Спринт 4.1-G (шаг G.2): Redis-инфраструктура для ActivityLocks-
    # (G.3) / Lobby- (4.1-H) / DAU- (4.1-I) репозиториев. Поле не
    # ``Optional`` — `RedisSettings()` без env всегда собирается
    # (local-dev defaults `redis://localhost:6379/0`). Реальное
    # подключение к Redis устанавливается только если
    # `BOT_ACTIVITY_LOCK_BACKEND=redis` (G.4) или явный feature-flag в
    # следующих PR-ах; иначе settings собран, но client не
    # инстанцируется.
    redis: RedisSettings = Field(default_factory=RedisSettings)
