"""Handler-ы регистрации/заморозки клана и авто-членства (Спринт 1.1.D).

Покрывает acceptance:
- 1.1.4 RegisterClan: бот добавлен в группу/супергруппу → запись в `clans`.
- 1.1.4 MigrateClanChatId: `message.migrate_to_chat_id` → обновление `chat_id`.
- 1.1.5 JoinClan: `chat_member` (зарегистрированный игрок виден в чате клана) → авто-членство;
  не зарегистрирован → инструкция «напишите боту в ЛС».
- 1.1.6 FreezeClan: бот удалён из чата → `status='frozen'` (история сохранена).

Handler-ы тонкие: они только переводят aiogram-апдейт в DTO и зовут
use-case. Локализация / форматирование ответов остаётся в этом модуле,
чтобы handler-ы не разбегались по всему проекту.
"""

from __future__ import annotations

from typing import Final

from aiogram import Bot, Router
from aiogram.types import (
    ChatMemberUpdated,
    Message,
)

from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.dto.inputs import (
    ClanChatKind,
    FreezeClanInput,
    JoinClanInput,
    MigrateClanChatIdInput,
    RegisterClanInput,
)

router = Router(name="registration")

# Статусы из ChatMemberUpdated.new_chat_member.status, при которых
# считаем, что бот «удалён» из чата.
_BOT_REMOVED_STATUSES: Final = frozenset({"left", "kicked"})
_BOT_PRESENT_STATUSES: Final = frozenset({"member", "administrator", "creator"})

JOIN_NOT_REGISTERED_RU = (
    "🍆 Привет! Похоже, ты ещё не зарегистрирован в Пипирик Варс.\n"
    "Открой бота в ЛС и нажми /start — после этого можешь пользоваться кланом."
)


def _coerce_clan_chat_kind(chat_type: str) -> ClanChatKind | None:
    """Приводит `chat.type` (`group`/`supergroup`/прочее) к `ClanChatKind`.

    `None` означает, что это не клановый чат (private/channel) и
    регистрация клана не применима.
    """
    if chat_type == "group":
        return "group"
    if chat_type == "supergroup":
        return "supergroup"
    return None


@router.my_chat_member()
async def handle_my_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    register_clan: RegisterClan,
    freeze_clan: FreezeClan,
) -> None:
    """Реагирует на изменение статуса самого бота в чате.

    - Бот добавлен в group/supergroup и стал `member`/`administrator`
      → `RegisterClan`.
    - Бот стал `left`/`kicked` → `FreezeClan` (если он раньше был в этом чате).
    """
    new_status = event.new_chat_member.status
    chat = event.chat
    chat_kind = _coerce_clan_chat_kind(chat.type)
    if chat_kind is None:
        return  # private/channel — не клан.

    if new_status in _BOT_PRESENT_STATUSES:
        # Бот в чате — регистрируем клан (или размораживаем).
        added_by = event.from_user.id if event.from_user is not None else bot.id
        await register_clan.execute(
            RegisterClanInput(
                chat_id=chat.id,
                chat_kind=chat_kind,
                title=chat.title or f"chat {chat.id}",
                added_by_tg_id=added_by,
            )
        )
        return

    if new_status in _BOT_REMOVED_STATUSES:
        await freeze_clan.execute(
            FreezeClanInput(
                chat_id=chat.id,
                reason=f"bot_status:{new_status}",
            )
        )


@router.chat_member()
async def handle_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    join_clan: JoinClan,
) -> None:
    """Реагирует на появление пользователя в чате клана.

    Обрабатываем только переход в `member`/`administrator`/`creator` для
    обычного пользователя (не бота). Если игрок зарегистрирован в ЛС —
    создаём `clan_members`-запись; иначе шлём инструкцию.
    """
    new = event.new_chat_member
    if new.status not in _BOT_PRESENT_STATUSES:
        return
    user = new.user
    if user.is_bot:
        return

    chat = event.chat
    if _coerce_clan_chat_kind(chat.type) is None:
        return

    result = await join_clan.execute(
        JoinClanInput(
            chat_id=chat.id,
            tg_id=user.id,
        )
    )
    if result.outcome == "not_registered":
        # Лучше не спамить в общий чат — отправляем личным сообщением.
        # Если у нас нет права писать в ЛС (пользователь не нажимал
        # /start), Telegram вернёт 403 — это поймает ErrorHandlerMiddleware.
        await bot.send_message(
            chat_id=user.id,
            text=JOIN_NOT_REGISTERED_RU,
        )


@router.message(lambda m: m.migrate_to_chat_id is not None)
async def handle_migrate_to(
    message: Message,
    migrate_clan: MigrateClanChatId,
) -> None:
    """Telegram превратил group в supergroup — мигрируем `chat_id`."""
    new_chat_id = message.migrate_to_chat_id
    if new_chat_id is None:  # pragma: no cover — фильтр гарантирует
        return
    await migrate_clan.execute(
        MigrateClanChatIdInput(
            old_chat_id=message.chat.id,
            new_chat_id=new_chat_id,
            new_chat_kind="supergroup",
        )
    )
