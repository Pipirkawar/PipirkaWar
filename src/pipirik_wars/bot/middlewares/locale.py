"""`LocaleMiddleware` — выбор локали для дальнейшего рендера.

Спринт 1.5.A: подключён `LocaleResolver` (ПД 1.5.2). Middleware
переводит `tg_identity.language_code` в `Locale("ru" | "en")` через
переданную при инициализации стратегию и кладёт результат в
`data["locale"]`. Сырой `language_code` сохраняется в
`data["telegram_language_code"]` — пригождается для
аналитики / логов / будущего опционального override-а.

Если стратегия не передана при инициализации — используется дефолт
`LocaleResolver()`, у которого `default = Locale("en")` (ПД 1.5.2 —
fallback EN). Это удобно в тестах, чтобы можно было создать middleware
без аргументов.

Handler-ы и презентеры читают локаль из `data["locale"]` и не должны
«прибивать» язык по месту.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from pipirik_wars.application.i18n import Locale, LocaleResolver
from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity

DATA_KEY = "locale"
TG_LANG_DATA_KEY = "telegram_language_code"


class LocaleMiddleware(BaseMiddleware):
    """Резолвит `Locale` по `tg_identity.language_code` через стратегию.

    Стратегию (`LocaleResolver`) можно переопределять в тестах /
    composition root-е. По умолчанию — `LocaleResolver()` (RU/EN +
    fallback EN, см. `application.i18n`).
    """

    def __init__(self, *, resolver: LocaleResolver | None = None) -> None:
        super().__init__()
        self._resolver = resolver or LocaleResolver()

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
        locale: Locale = self._resolver.resolve(tg_lang=tg_lang)
        data[DATA_KEY] = locale
        data[TG_LANG_DATA_KEY] = tg_lang
        return await handler(event, data)
