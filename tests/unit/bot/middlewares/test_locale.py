"""Юнит-тесты `LocaleMiddleware` (Спринт 1.5.A)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import TelegramObject

from pipirik_wars.application.i18n import DEFAULT_LOCALE, Locale, LocaleResolver
from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.bot.middlewares.locale import (
    DATA_KEY as LOCALE_KEY,
    TG_LANG_DATA_KEY,
    LocaleMiddleware,
)


@pytest.mark.asyncio
class TestLocaleMiddleware:
    async def _call(
        self,
        identity: TgIdentity | None,
        *,
        resolver: LocaleResolver | None = None,
    ) -> dict[str, Any]:
        mw = LocaleMiddleware(resolver=resolver)
        data: dict[str, Any] = {AUTH_DATA_KEY: identity}
        handler = AsyncMock(return_value="ok")
        event = MagicMock(spec=TelegramObject)
        result = await mw(handler, event, data)
        assert result == "ok"
        handler.assert_awaited_once_with(event, data)
        return data

    async def test_russian_language_code_resolves_to_ru(self) -> None:
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code="ru")
        data = await self._call(identity)
        assert data[LOCALE_KEY] == Locale("ru")
        assert data[TG_LANG_DATA_KEY] == "ru"

    async def test_english_language_code_resolves_to_en(self) -> None:
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code="en-US")
        data = await self._call(identity)
        assert data[LOCALE_KEY] == Locale("en")
        assert data[TG_LANG_DATA_KEY] == "en-US"

    async def test_unknown_language_code_falls_back_to_default(self) -> None:
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code="fr")
        data = await self._call(identity)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE
        assert data[TG_LANG_DATA_KEY] == "fr"

    async def test_no_language_code_falls_back_to_default(self) -> None:
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code=None)
        data = await self._call(identity)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE
        assert data[TG_LANG_DATA_KEY] is None

    async def test_no_identity_still_sets_default_locale(self) -> None:
        data = await self._call(identity=None)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE
        assert data[TG_LANG_DATA_KEY] is None

    async def test_custom_resolver_is_respected(self) -> None:
        custom = LocaleResolver(default=Locale("ru"))
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code="zh")
        data = await self._call(identity, resolver=custom)
        assert data[LOCALE_KEY] == Locale("ru")
