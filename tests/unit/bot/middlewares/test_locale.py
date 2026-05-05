"""Юнит-тесты `LocaleMiddleware` (Спринт 1.5.A → 1.5.F).

С 1.5.F middleware принимает опциональный `IPlayerLocaleResolver` и
имеет приоритетную цепочку:

1. `users.locale_override` (из БД через резолвер).
2. `tg.language_code` через `LocaleResolver`.
3. `LocaleResolver.default`.
"""

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
from tests.fakes import FakePlayerLocaleResolver


@pytest.mark.asyncio
class TestLocaleMiddleware:
    async def _call(
        self,
        identity: TgIdentity | None,
        *,
        resolver: LocaleResolver | None = None,
        player_locale_resolver: FakePlayerLocaleResolver | None = None,
    ) -> dict[str, Any]:
        mw = LocaleMiddleware(
            resolver=resolver,
            player_locale_resolver=player_locale_resolver,
        )
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

    async def test_player_override_wins_over_tg_language_code(self) -> None:
        """1.5.F: locale_override приоритет над tg.language_code."""
        identity = TgIdentity(
            tg_user_id=42,
            chat_id=2,
            chat_kind="private",
            language_code="en-US",
        )
        resolver = FakePlayerLocaleResolver()
        resolver.set_override(42, Locale("ru"))
        data = await self._call(identity, player_locale_resolver=resolver)
        assert data[LOCALE_KEY] == Locale("ru")
        assert data[TG_LANG_DATA_KEY] == "en-US"
        assert resolver.calls == [42]

    async def test_player_override_missing_falls_back_to_tg(self) -> None:
        """Если override не выставлен — фолбэк на tg.language_code."""
        identity = TgIdentity(
            tg_user_id=42,
            chat_id=2,
            chat_kind="private",
            language_code="ru",
        )
        resolver = FakePlayerLocaleResolver()
        # override не задан → resolve_for_tg_id вернёт None.
        data = await self._call(identity, player_locale_resolver=resolver)
        assert data[LOCALE_KEY] == Locale("ru")
        assert resolver.calls == [42]

    async def test_player_override_resolver_skipped_without_identity(self) -> None:
        """Без TgIdentity (нет tg_user_id) резолвер не вызывается."""
        resolver = FakePlayerLocaleResolver()
        data = await self._call(identity=None, player_locale_resolver=resolver)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE
        assert resolver.calls == []

    async def test_player_override_falls_back_when_unsupported(self) -> None:
        """Если резолвер вернул `None`, а tg.language_code тоже мусор —
        фолбэк на DEFAULT."""
        identity = TgIdentity(
            tg_user_id=42,
            chat_id=2,
            chat_kind="private",
            language_code="zh-CN",
        )
        resolver = FakePlayerLocaleResolver()
        data = await self._call(identity, player_locale_resolver=resolver)
        assert data[LOCALE_KEY] == DEFAULT_LOCALE
