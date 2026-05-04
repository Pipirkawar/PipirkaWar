"""Юнит-тесты `ThrottleMiddleware`."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.bot.middlewares.throttle import (
    THROTTLE_REPLY_RU,
    ThrottleMiddleware,
)
from pipirik_wars.infrastructure.rate_limit import IRateLimiter


class _AlwaysAcceptLimiter(IRateLimiter):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def try_acquire(self, *, key: str) -> bool:
        self.calls.append(key)
        return True


class _AlwaysRejectLimiter(IRateLimiter):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def try_acquire(self, *, key: str) -> bool:
        self.calls.append(key)
        return False


def _identity(user_id: int = 1, chat_id: int = 2) -> TgIdentity:
    return TgIdentity(tg_user_id=user_id, chat_id=chat_id, chat_kind="private", language_code=None)


def _message_mock() -> MagicMock:
    """`spec=Message` нужно, чтобы прошёл `isinstance(event, Message)`
    в production-коде; `answer` подменяем на `AsyncMock`, т.к. spec
    отдаёт sync-метод."""
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
class TestThrottleMiddleware:
    async def test_passes_through_when_acquired(self) -> None:
        limiter = _AlwaysAcceptLimiter()
        mw = ThrottleMiddleware(limiter=limiter)
        handler = AsyncMock(return_value="handler-ok")
        event = _message_mock()
        data: dict[str, Any] = {AUTH_DATA_KEY: _identity(7, 13)}
        result = await mw(handler, cast(Message, event), data)
        assert result == "handler-ok"
        assert limiter.calls == ["7:13"]
        handler.assert_awaited_once_with(event, data)
        event.answer.assert_not_awaited()

    async def test_drops_with_reply_when_rejected_for_message(self) -> None:
        limiter = _AlwaysRejectLimiter()
        mw = ThrottleMiddleware(limiter=limiter)
        handler = AsyncMock()
        event = _message_mock()
        data: dict[str, Any] = {AUTH_DATA_KEY: _identity(1, 2)}
        result = await mw(handler, cast(Message, event), data)
        assert result is None
        handler.assert_not_awaited()
        event.answer.assert_awaited_once_with(THROTTLE_REPLY_RU)

    async def test_drops_silently_for_non_message(self) -> None:
        limiter = _AlwaysRejectLimiter()
        mw = ThrottleMiddleware(limiter=limiter)
        handler = AsyncMock()
        event = MagicMock(spec=TelegramObject)
        data: dict[str, Any] = {AUTH_DATA_KEY: _identity()}
        result = await mw(handler, event, data)
        assert result is None
        handler.assert_not_awaited()

    async def test_no_identity_skips_throttle(self) -> None:
        limiter = _AlwaysRejectLimiter()
        mw = ThrottleMiddleware(limiter=limiter)
        handler = AsyncMock(return_value="ok")
        event = _message_mock()
        data: dict[str, Any] = {AUTH_DATA_KEY: None}
        result = await mw(handler, cast(Message, event), data)
        assert result == "ok"
        assert limiter.calls == []
        handler.assert_awaited_once_with(event, data)
