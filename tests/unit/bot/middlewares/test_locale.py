"""Юнит-тесты `LocaleMiddleware`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.bot.middlewares.locale import (
    DATA_KEY as LOCALE_KEY,
    DEFAULT_LOCALE,
    TG_LANG_DATA_KEY,
    LocaleMiddleware,
)


@pytest.mark.asyncio
class TestLocaleMiddleware:
    async def _call(self, identity: TgIdentity | None) -> dict[str, Any]:
        mw = LocaleMiddleware()
        data: dict[str, Any] = {AUTH_DATA_KEY: identity}
        handler = AsyncMock(return_value="ok")
        event = MagicMock(spec=TelegramObject)
        result = await mw(handler, event, data)
        assert result == "ok"
        handler.assert_awaited_once_with(event, data)
        return data

    async def test_default_locale_is_ru(self) -> None:
        identity = TgIdentity(tg_user_id=1, chat_id=2, chat_kind="private", language_code="en")
        data = await self._call(identity)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE == "ru"
        assert data[TG_LANG_DATA_KEY] == "en"

    async def test_no_identity_still_sets_locale(self) -> None:
        data = await self._call(identity=None)
        assert data[LOCALE_KEY] == "ru"
        assert data[TG_LANG_DATA_KEY] is None
