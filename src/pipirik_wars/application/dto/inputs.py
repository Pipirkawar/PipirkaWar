"""DTO входных данных use-case-ов.

Все валидации — pydantic-side; в use-case бизнес-логика уже работает
с проверенным объектом. На каждый отказ — конкретное поле и причина
(человекочитаемое сообщение через `bot/`-локализацию в Спринте 1.1+).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# В геймплее tg_id всегда положительный; ботов и каналов мы здесь не валидируем.
PositiveTgId = int

# Telegram chat_kind для регистрации клана. Личные/каналы здесь не имеют
# смысла — клан = группа или супергруппа.
ClanChatKind = Literal["group", "supergroup"]


class _StrictBase(BaseModel):
    """Базовый DTO: запрещаем лишние поля и неявные конверсии."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )


class RegisterPlayerInput(_StrictBase):
    """Регистрация нового игрока через ЛС бота.

    `referrer_tg_id` — `tg_id` пригласившего; `None`, если пришли без рефки.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id")
    username: str | None = Field(
        default=None,
        max_length=64,
        description="@username без @, может быть None",
    )
    locale: str = Field(
        default="ru",
        pattern=r"^[a-z]{2}(_[A-Z]{2})?$",
        description="ISO-код локали, например 'ru' или 'en_US'",
    )
    referrer_tg_id: PositiveTgId | None = Field(default=None, gt=0)


class RegisterClanInput(_StrictBase):
    """Регистрация клана при добавлении бота в группу.

    Use-case `RegisterClan` идемпотентен: если клан с таким `chat_id`
    уже существует и `frozen` — он размораживается; если `active` —
    no-op.
    """

    chat_id: int = Field(description="Telegram chat_id (отрицательный для групп)")
    chat_kind: ClanChatKind = Field(description='Тип чата: "group" или "supergroup".')
    title: str = Field(min_length=1, max_length=128)
    added_by_tg_id: PositiveTgId = Field(gt=0)


class MigrateClanChatIdInput(_StrictBase):
    """Миграция клана с group → supergroup (Telegram меняет `chat_id`).

    Передаётся из bot-handler-а, который ловит
    `message.migrate_to_chat_id`.
    """

    old_chat_id: int = Field(description="Прежний chat_id (group)")
    new_chat_id: int = Field(description="Новый chat_id (supergroup, обычно `-100…`)")
    new_chat_kind: ClanChatKind = Field(description='Тип нового чата (обычно "supergroup")')


class JoinClanInput(_StrictBase):
    """Добавление зарегистрированного игрока в клан-чат.

    Срабатывает при `chat_member`/`my_chat_member`, когда уже
    зарегистрированный (через ЛС) игрок виден в чате клана.
    """

    chat_id: int = Field(description="Telegram chat_id клана")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FreezeClanInput(_StrictBase):
    """Заморозка клана при удалении бота из чата (Спринт 1.1.6)."""

    chat_id: int = Field(description="Telegram chat_id клана")
    reason: str = Field(
        default="bot_removed_from_chat",
        min_length=1,
        max_length=255,
    )


class GrantLengthInput(_StrictBase):
    """Админская выдача длины (обязательная причина → audit_log)."""

    target_tg_id: PositiveTgId = Field(gt=0)
    delta_cm: int = Field(description="Может быть отрицательным; ноль запрещён")
    reason: str = Field(min_length=3, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=255)


class StartForestRunInput(_StrictBase):
    """Старт похода в лес (Спринт 1.3.B).

    Игрок идентифицируется `tg_id`, как и во всех остальных входных
    DTO. Внутренний `player.id` use-case достанет через
    `IPlayerRepository.get_by_tg_id` — это даёт единый внешний контракт
    для bot-handler-ов, которые видят только Telegram-id.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class FinishForestRunInput(_StrictBase):
    """Финиш похода в лес (Спринт 1.3.C).

    На вход — `run_id` записи `forest_runs`. Источник вызова —
    APScheduler-job, который Запланировал `StartForestRun` на `ends_at`.
    """

    run_id: int = Field(gt=0, description="forest_runs.id")


class ApplyForestNameDropInput(_StrictBase):
    """Применить выпавшее в лесу имя (Спринт 1.3.D, ГДД §2.5 / §8.2).

    Используется кнопкой «Заменить» на сообщении «вернулся из леса»,
    когда у игрока уже было имя и `FinishForestRun` оставил `NameDrop`
    без auto-apply. Use-case `ApplyForestNameDrop` делает фактическую
    замену с аудитом.

    `tg_id` сверяется с `forest_runs.player_id` через
    `IPlayerRepository.get_by_tg_id`: чужой пользователь не может
    применить чужой дроп.
    """

    run_id: int = Field(gt=0, description="forest_runs.id")
    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")


class UpgradeThicknessInput(_StrictBase):
    """Прокачка уровня толщины (Спринт 1.4.A, ГДД §3.2).

    Use-case `UpgradeThickness` сам считает стоимость по
    `balance.yaml::thickness.cost_*`, делает проверку правила 20 см
    через `progression.require_spend(THICKNESS_UPGRADE)` и поднимает
    `player.thickness` на 1.

    `expected_cost_cm` — опциональный «контракт» от UI: если он отличается
    от свежепосчитанной стоимости, use-case бросает `ConcurrencyError`.
    Это защита от ситуации «balance.yaml перегружен между показом
    подтверждения и нажатием Подтвердить» (см. Спринт 1.4.B при горячей
    перезагрузке баланса). `None` — пропустить проверку.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")
    expected_cost_cm: int | None = Field(
        default=None,
        gt=0,
        description="Стоимость, которую UI показал пользователю; для защиты от race",
    )


class InvokeOracleInput(_StrictBase):
    """Вызов `/oracle` (Спринт 1.4.B, ГДД §11).

    Локаль определяется `LocaleMiddleware` и пробрасывается до
    use-case-а; `IOracleTemplateProvider` подтянет каталог шаблонов
    нужного языка. Кулдаун (1 раз в сутки по Москве) считается на
    стороне use-case-а через `IClock.moscow_date()` и
    `IOracleHistoryRepository`.
    """

    tg_id: PositiveTgId = Field(gt=0, description="Telegram user_id игрока")
    locale: str = Field(
        default="ru",
        pattern=r"^[a-z]{2}(_[A-Z]{2})?$",
        description="Локаль каталога предсказаний (например, 'ru' или 'en')",
    )
