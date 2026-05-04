"""Юнит-тесты `/start` handler-а (acceptance 1.1.1).

Проверяем `_reply_text_for(...)` (чистая функция, легко покрывается)
и сам handler `handle_start` (с моками `Message` и `TgIdentity`).
Acceptance criteria из `development_plan.md` §3 / Спринт 1.1.1:
> `/start` отвечает в ЛС, в группе и в супергруппе.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.bot.handlers.start import (
    REPLY_GROUP_RU,
    REPLY_OTHER_RU,
    REPLY_PRIVATE_RU,
    _reply_text_for,
    handle_start,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity


class TestReplyTextFor:
    def test_private(self) -> None:
        assert _reply_text_for("private") == REPLY_PRIVATE_RU

    def test_group(self) -> None:
        assert _reply_text_for("group") == REPLY_GROUP_RU

    def test_supergroup(self) -> None:
        assert _reply_text_for("supergroup") == REPLY_GROUP_RU

    def test_channel_falls_back_to_other(self) -> None:
        assert _reply_text_for("channel") == REPLY_OTHER_RU

    def test_unknown_falls_back_to_other(self) -> None:
        assert _reply_text_for("totally_new_kind") == REPLY_OTHER_RU


def _build_message_mock(chat_type: str = "private") -> MagicMock:
    """Возвращает «duck-typed» Message для подачи в handler.

    Возвращаем `MagicMock`, а не `Message`, чтобы mypy не ругался на
    `assert_awaited_once_with(...)`; в `handle_start(...)` кастуем
    обратно в `Message`. Runtime-поведение идентично, т.к. handler
    обращается только к `message.chat.type` и `message.answer(...)`.
    """
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str) -> TgIdentity:
    return TgIdentity(tg_user_id=1, chat_id=42, chat_kind=chat_kind, language_code=None)


@pytest.mark.asyncio
class TestHandleStart:
    async def test_replies_in_private(self) -> None:
        msg = _build_message_mock("private")
        await handle_start(cast(Message, msg), _identity("private"))
        msg.answer.assert_awaited_once_with(REPLY_PRIVATE_RU)

    async def test_replies_in_group(self) -> None:
        msg = _build_message_mock("group")
        await handle_start(cast(Message, msg), _identity("group"))
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_replies_in_supergroup(self) -> None:
        msg = _build_message_mock("supergroup")
        await handle_start(cast(Message, msg), _identity("supergroup"))
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_falls_back_to_message_chat_type_if_no_identity(self) -> None:
        msg = _build_message_mock("private")
        await handle_start(cast(Message, msg), None)
        msg.answer.assert_awaited_once_with(REPLY_PRIVATE_RU)
