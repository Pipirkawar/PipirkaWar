"""`LocaleMiddleware` — выбор локали для дальнейшего рендера.

Спринт 1.5.A: подключён `LocaleResolver` (ПД 1.5.2). Middleware
переводит `tg_identity.language_code` в `Locale("ru" | "en")` через
переданную при инициализации стратегию и кладёт результат в
`data["locale"]`.

Спринт 1.5.F: расширен порядком приоритета `player.locale_override →
tg.language_code → DEFAULT_LOCALE`. Если игрок выставил `/lang ru|en`,
override из `users.locale_override` имеет высший приоритет — даже если
у Telegram-аккаунта `language_code = "en-US"`. Если override не задан
(или `IPlayerLocaleResolver` не передан в middleware — для тестов),
работает старая стратегия `LocaleResolver(tg_lang) → Locale`.

Сырой `language_code` всё равно сохраняется в
`data["telegram_language_code"]` — пригождается для аналитики / логов.

Handler-ы и презентеры читают локаль из `data["locale"]` и не должны
«прибивать» язык по месту.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from pipirik_wars.application.i18n import (
    IPlayerLocaleResolver,
    Locale,
    LocaleResolver,
)
from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity

DATA_KEY = "locale"
TG_LANG_DATA_KEY = "telegram_language_code"


class LocaleMiddleware(BaseMiddleware):
    """Резолвит `Locale` по приоритету:

    1. `users.locale_override` (если игрок зарегистрирован и выставил
       `/lang`) — через `IPlayerLocaleResolver`.
    2. `tg_identity.language_code` через `LocaleResolver`.
    3. `LocaleResolver.default` (`Locale("en")`).

    `IPlayerLocaleResolver` опциональный: если не передан, шаг 1
    пропускается. Это удобно в тестах и в Спринтах до 1.5.F.
    """

    def __init__(
        self,
        *,
        resolver: LocaleResolver | None = None,
        player_locale_resolver: IPlayerLocaleResolver | None = None,
    ) -> None:
        super().__init__()
        self._resolver = resolver or LocaleResolver()
        self._player_locale_resolver = player_locale_resolver

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity = data.get(AUTH_DATA_KEY)
        tg_lang: str | None = None
        tg_id: int | None = None
        if isinstance(identity, TgIdentity):
            tg_lang = identity.language_code
            tg_id = identity.tg_user_id

        locale: Locale | None = None
        if self._player_locale_resolver is not None and tg_id is not None:
            locale = await self._player_locale_resolver.resolve_for_tg_id(tg_id)
        if locale is None:
            locale = self._resolver.resolve(tg_lang=tg_lang)

        data[DATA_KEY] = locale
        data[TG_LANG_DATA_KEY] = tg_lang
        return await handler(event, data)
