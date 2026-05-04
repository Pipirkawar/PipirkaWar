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
