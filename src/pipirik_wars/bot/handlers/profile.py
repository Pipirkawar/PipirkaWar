"""`/profile` handler (Спринт 1.1.9, ГДД §2.2).

Acceptance:
- Только в ЛС: в группе/супергруппе бот шлёт инструкцию «открой ЛС».
  Это тот же контракт, что и у `/start` — клановые чаты не место
  для просмотра карточки игрока (UX + privacy).
- Если игрок не зарегистрирован — handler шлёт текст-инструкцию
  с напоминанием нажать `/start` в ЛС.
- Иначе — рендерит карточку через `bot/presenters/profile.py`.

Все ошибки use-case-а ловит `ErrorHandlerMiddleware`; здесь handler
не пытается обрабатывать `DomainError`-ы вручную.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import render_profile_card

router = Router(name="profile")

REPLY_GROUP_RU = "🍆 Команда /profile доступна только в личке бота. Открой приватный чат и повтори."
REPLY_OTHER_RU = "🍆 Команда /profile доступна только в личке бота."
REPLY_NOT_REGISTERED_RU = (
    "🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате, и карточка появится."
)


@router.message(Command("profile"))
async def handle_profile(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
) -> None:
    """Отвечает на `/profile` — рисует карточку персонажа в ЛС."""
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(REPLY_GROUP_RU)
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_OTHER_RU)
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(REPLY_NOT_REGISTERED_RU)
        return
    await message.answer(render_profile_card(view))
