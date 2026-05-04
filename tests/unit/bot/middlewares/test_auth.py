"""Юнит-тесты `AuthMiddleware`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberUpdated,
    Message,
    TelegramObject,
    User,
)

from pipirik_wars.bot.middlewares.auth import DATA_KEY, AuthMiddleware, TgIdentity


def _build_message(
    *,
    user_id: int = 100,
    chat_id: int = 200,
    chat_type: str = "private",
    language_code: str | None = "ru",
    no_user: bool = False,
) -> Message:
    msg = MagicMock(spec=Message)
    msg.from_user = (
        None
        if no_user
        else User(id=user_id, is_bot=False, first_name="N", language_code=language_code)
    )
    msg.chat = Chat(id=chat_id, type=chat_type)
    return msg


@pytest.mark.asyncio
class TestAuthMiddleware:
    async def _call(self, mw: AuthMiddleware, event: TelegramObject) -> dict[str, Any]:
        data: dict[str, Any] = {}
        handler = AsyncMock(return_value="ok")
        result = await mw(handler, event, data)
        assert result == "ok"
        handler.assert_awaited_once_with(event, data)
        return data

    async def test_extracts_identity_from_message(self) -> None:
        mw = AuthMiddleware()
        msg = _build_message(user_id=42, chat_id=-100, chat_type="supergroup")
        data = await self._call(mw, msg)
        identity = data[DATA_KEY]
        assert isinstance(identity, TgIdentity)
        assert identity.tg_user_id == 42
        assert identity.chat_id == -100
        assert identity.chat_kind == "supergroup"
        assert identity.language_code == "ru"

    async def test_message_without_user_yields_none(self) -> None:
        mw = AuthMiddleware()
        msg = _build_message(no_user=True)
        data = await self._call(mw, msg)
        assert data[DATA_KEY] is None

    async def test_extracts_identity_from_callback_query(self) -> None:
        mw = AuthMiddleware()
        msg = _build_message(chat_id=-101, chat_type="group")
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = User(id=7, is_bot=False, first_name="N", language_code="en")
        cb.message = msg
        data = await self._call(mw, cb)
        identity = data[DATA_KEY]
        assert isinstance(identity, TgIdentity)
        assert identity.tg_user_id == 7
        assert identity.chat_id == -101
        assert identity.chat_kind == "group"
        assert identity.language_code == "en"

    async def test_callback_without_message_or_user_yields_none(self) -> None:
        mw = AuthMiddleware()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = None
        cb.message = None
        data = await self._call(mw, cb)
        assert data[DATA_KEY] is None

    async def test_extracts_identity_from_chat_member_updated(self) -> None:
        mw = AuthMiddleware()
        ev = MagicMock(spec=ChatMemberUpdated)
        ev.from_user = User(id=99, is_bot=False, first_name="A")
        ev.chat = Chat(id=-100200, type="supergroup")
        data = await self._call(mw, ev)
        identity = data[DATA_KEY]
        assert isinstance(identity, TgIdentity)
        assert identity.tg_user_id == 99
        assert identity.chat_id == -100200
        assert identity.chat_kind == "supergroup"

    async def test_unknown_event_yields_none(self) -> None:
        mw = AuthMiddleware()
        ev = MagicMock(spec=TelegramObject)
        data = await self._call(mw, ev)
        assert data[DATA_KEY] is None
