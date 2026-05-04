"""Юнит-тесты `ErrorHandlerMiddleware`."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, TelegramObject

from pipirik_wars.bot.middlewares.error_handler import (
    DOMAIN_ERROR_REPLY_RU,
    UNEXPECTED_REPLY_RU,
    ErrorHandlerMiddleware,
)
from pipirik_wars.shared.errors import DomainError


class _SomeDomainError(DomainError):
    pass


def _message_mock() -> MagicMock:
    """`spec=Message` нужно для `isinstance(event, Message)` в проде."""
    msg = MagicMock(spec=Message)
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
class TestErrorHandlerMiddleware:
    async def test_passthrough_on_success(self) -> None:
        mw = ErrorHandlerMiddleware()
        handler = AsyncMock(return_value="value")
        event = _message_mock()
        data: dict[str, Any] = {}
        assert await mw(handler, cast(Message, event), data) == "value"
        event.answer.assert_not_awaited()

    async def test_domain_error_replies_to_user(self) -> None:
        mw = ErrorHandlerMiddleware()
        handler = AsyncMock(side_effect=_SomeDomainError("длина не подходит"))
        event = _message_mock()
        data: dict[str, Any] = {}
        result = await mw(handler, cast(Message, event), data)
        assert result is None
        event.answer.assert_awaited_once_with(
            DOMAIN_ERROR_REPLY_RU.format(message="длина не подходит")
        )

    async def test_domain_error_silent_for_non_message(self) -> None:
        mw = ErrorHandlerMiddleware()
        handler = AsyncMock(side_effect=_SomeDomainError("..."))
        event = MagicMock(spec=TelegramObject)
        data: dict[str, Any] = {}
        result = await mw(handler, event, data)
        assert result is None

    async def test_unexpected_error_replies_and_reraises(self) -> None:
        mw = ErrorHandlerMiddleware()
        boom = RuntimeError("неожиданное")
        handler = AsyncMock(side_effect=boom)
        event = _message_mock()
        data: dict[str, Any] = {}
        with pytest.raises(RuntimeError, match="неожиданное"):
            await mw(handler, cast(Message, event), data)
        event.answer.assert_awaited_once_with(UNEXPECTED_REPLY_RU)
