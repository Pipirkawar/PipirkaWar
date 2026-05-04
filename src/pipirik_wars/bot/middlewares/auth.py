"""`AuthMiddleware` — извлечение Telegram-идентичности из апдейта.

Этот middleware **не делает** проверку прав (требуемая длина, клан и
т.п.) — это работа декораторов `requires_*` из `application.auth`.
Здесь же мы только превращаем сырой aiogram-event в стабильную
структуру `TgIdentity`, которую дальше использует handler / use-case.

Если в апдейте нет `from_user` (например, сервисное `my_chat_member`
без инициатора), middleware пропускает событие как есть, не выбрасывая
исключения — фильтрация таких случаев — на стороне конкретных handler-ов.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, TelegramObject

DATA_KEY = "tg_identity"


@dataclass(frozen=True, slots=True)
class TgIdentity:
    """Минимальная Telegram-идентичность, выдернутая из апдейта.

    `chat_kind` — `"private" | "group" | "supergroup" | "channel"`.
    Использование строки (а не enum-а) намеренно: handler-ы делают
    дальше прямые сравнения с этими литералами, не закрепляя себя за
    domain-моделью `ChatKind` (которая содержит только клановые
    варианты `group / supergroup`).
    """

    tg_user_id: int
    chat_id: int
    chat_kind: str
    language_code: str | None


def _extract(event: TelegramObject) -> TgIdentity | None:
    if isinstance(event, Message):
        if event.from_user is None:
            return None
        return TgIdentity(
            tg_user_id=event.from_user.id,
            chat_id=event.chat.id,
            chat_kind=event.chat.type,
            language_code=event.from_user.language_code,
        )
    if isinstance(event, CallbackQuery):
        if event.message is None or event.from_user is None:
            return None
        return TgIdentity(
            tg_user_id=event.from_user.id,
            chat_id=event.message.chat.id,
            chat_kind=event.message.chat.type,
            language_code=event.from_user.language_code,
        )
    if isinstance(event, ChatMemberUpdated):
        return TgIdentity(
            tg_user_id=event.from_user.id,
            chat_id=event.chat.id,
            chat_kind=event.chat.type,
            language_code=event.from_user.language_code,
        )
    return None


class AuthMiddleware(BaseMiddleware):
    """Кладёт в `data["tg_identity"]` объект `TgIdentity | None`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data[DATA_KEY] = _extract(event)
        return await handler(event, data)
