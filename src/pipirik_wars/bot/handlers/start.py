"""`/start` handler-stub (Спринт 1.1.C, acceptance 1.1.1).

Acceptance criteria из `development_plan.md` Спринт 1.1.1:
> `/start` отвечает в ЛС, в группе и в супергруппе.

Сейчас фактической регистрации не происходит — это работа PR 1.1.D
(use-case `RegisterPlayer`). Здесь handler просто шлёт текст-стаб с
пояснением, в каком режиме команда выполнена. В ЛС подсказывает, что
скоро здесь будет регистрация игрока; в группе — что сначала нужно
зарегистрироваться в личке, а потом добавить бота в группу для
регистрации клана.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from pipirik_wars.bot.middlewares import TgIdentity

router = Router(name="start")

REPLY_PRIVATE_RU = (
    "🍆 Привет! Это бот «Пипирик Варс».\n\n"
    "Скоро здесь появится регистрация игрока (`/register`). "
    "Пока что бот в разработке — следи за обновлениями."
)
REPLY_GROUP_RU = (
    "🍆 «Пипирик Варс» здесь!\n\n"
    "1. Сначала зарегистрируйся в личке бота: открой приватный чат и нажми /start.\n"
    "2. Потом добавь меня в группу как админа — это превратит чат в клан."
)
REPLY_OTHER_RU = "🍆 «Пипирик Варс» здесь. Команда /start доступна в ЛС или в группе."


def _reply_text_for(chat_kind: str) -> str:
    """Маппит chat_type из Telegram на текст ответа."""
    if chat_kind == "private":
        return REPLY_PRIVATE_RU
    if chat_kind in ("group", "supergroup"):
        return REPLY_GROUP_RU
    return REPLY_OTHER_RU


@router.message(CommandStart())
async def handle_start(message: Message, tg_identity: TgIdentity | None) -> None:
    """Отвечает на `/start` в любом типе чата.

    `tg_identity` приходит от `AuthMiddleware`. Если его нет — отвечаем
    нейтрально по `message.chat.type`. На уровне доменной логики этот
    handler пока ничего не делает (регистрация — в 1.1.D).
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    await message.answer(_reply_text_for(chat_kind))
