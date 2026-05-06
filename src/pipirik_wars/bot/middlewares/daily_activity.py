"""`DailyActivityMiddleware` — запись активности игрока в `daily_active`.

Спринт 2.3.F.1 (ПД 2.3.7). На каждое входящее Telegram-сообщение от
зарегистрированного игрока в групповом / супергрупповом чате клана
middleware зовёт `RecordPlayerActivity` — UPSERT в `daily_active`
по PK `(moscow_date, user_id)`. Эта таблица потом читается
`DailyHeadService.assign_or_get(...)` для preflight-проверки
`min_active_members` (ГДД §6.1.2).

Что middleware **не** делает:
- не пишет активность в private-чатах (бот×игрок) — личные команды
  не должны влиять на «активных за 7 дней» в клане;
- не пишет активность в каналах (`chat_kind == "channel"`);
- не пишет активность для callback-апдейтов и `chat_member` —
  цель таблицы именно «писал ли игрок в клан-чат», а не «нажимал
  ли в боте кнопки»;
- не падает команду пользователя, если запись провалилась — ошибка
  логируется через стандартный `logging`-логгер на уровне `WARNING`,
  а handler выполняется как обычно.

Регистрируется **после** `AuthMiddleware` (нужен `tg_identity`) и
**до** `ThrottleMiddleware` — throttle-проверка не должна гасить
запись активности (на rate-limit-е игрок всё равно был активен).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from pipirik_wars.application.daily_head import RecordPlayerActivity
from pipirik_wars.application.dto.inputs import RecordPlayerActivityInput
from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity

_log = logging.getLogger(__name__)

_TRACKED_CHAT_KINDS = frozenset({"group", "supergroup"})


class DailyActivityMiddleware(BaseMiddleware):
    """Записывает активность игрока в `daily_active` на каждое сообщение.

    Применяется **только** к `dispatcher.message` — `callback_query`,
    `chat_member`, `my_chat_member` и т.п. не считаются «активностью
    в клан-чате» для preflight-а Главы клана дня.
    """

    __slots__ = ("_use_case",)

    def __init__(self, *, use_case: RecordPlayerActivity) -> None:
        super().__init__()
        self._use_case = use_case

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # 1. Только сообщения; не callback / chat_member.
        if not isinstance(event, Message):
            return await handler(event, data)

        # 2. Только групповые / супергрупповые чаты.
        identity = data.get(AUTH_DATA_KEY)
        if not isinstance(identity, TgIdentity):
            return await handler(event, data)
        if identity.chat_kind not in _TRACKED_CHAT_KINDS:
            return await handler(event, data)

        # 3. Запись активности — best-effort; ошибки не пробрасываем,
        # чтобы не ронять команду пользователя.
        try:
            await self._use_case.execute(
                RecordPlayerActivityInput(tg_user_id=identity.tg_user_id),
            )
        except Exception:
            _log.warning(
                "daily_activity record failed for tg_user_id=%s chat_id=%s",
                identity.tg_user_id,
                identity.chat_id,
                exc_info=True,
            )

        return await handler(event, data)


__all__ = ["DailyActivityMiddleware"]
