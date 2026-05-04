"""`LocaleMiddleware` — выбор локали для дальнейшего рендера.

Сейчас (1.1.C) всегда возвращает `"ru"` — i18n-loader (fluent) и
real-locale-resolution появятся позже (Фаза 2). Middleware зарезервирован,
чтобы handler-ы и presenter-ы не «прибивали» язык по месту, а брали из
`data["locale"]`.

Если в `tg_identity.language_code` есть значение — оставим его на будущее
в `data["telegram_language_code"]`; финальный язык рендера всё равно `ru`,
пока не подключён `fluent`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity

DEFAULT_LOCALE = "ru"
DATA_KEY = "locale"
TG_LANG_DATA_KEY = "telegram_language_code"


class LocaleMiddleware(BaseMiddleware):
    """Сейчас всегда выставляет `locale="ru"`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity = data.get(AUTH_DATA_KEY)
        tg_lang: str | None = None
        if isinstance(identity, TgIdentity):
            tg_lang = identity.language_code
        data[DATA_KEY] = DEFAULT_LOCALE
        data[TG_LANG_DATA_KEY] = tg_lang
        return await handler(event, data)
