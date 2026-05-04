"""`ThrottleMiddleware` — общий rate-limiter поверх `IRateLimiter`.

Ключ бакета формируется как `f"{tg_user_id}:{chat_id}"` — лимит на
пару (пользователь × чат). Это значит, что игрок одновременно может
дёргать команды в нескольких чатах независимо, но в пределах одного
чата лимит общий (защита от ковровой бомбардировки `/profile`).

Если `try_acquire()` вернул `False`:
- Для `Message` — отвечаем коротким сообщением о превышении лимита.
- Для остальных событий — просто молча проглатываем (handler не вызывается).

`tg_identity` обязателен (его кладёт `AuthMiddleware`); если его нет
(например, апдейт без user-а), middleware пропускает throttle вовсе —
ловить такие события на спам бессмысленно (Telegram сам не пришлёт
их в количестве).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.infrastructure.rate_limit import IRateLimiter

THROTTLE_REPLY_RU = "⏳ Слишком быстро, подожди секунду."


class ThrottleMiddleware(BaseMiddleware):
    """Применяет `IRateLimiter` к каждому пропускаемому событию."""

    __slots__ = ("_limiter",)

    def __init__(self, *, limiter: IRateLimiter) -> None:
        self._limiter = limiter

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity = data.get(AUTH_DATA_KEY)
        if not isinstance(identity, TgIdentity):
            return await handler(event, data)
        key = f"{identity.tg_user_id}:{identity.chat_id}"
        if self._limiter.try_acquire(key=key):
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(THROTTLE_REPLY_RU)
        return None
