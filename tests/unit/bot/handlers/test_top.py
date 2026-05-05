"""Юнит-тесты `/top`-handler-а (Спринт 1.4.C, ПД 1.4.6)."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.top import GetTopPlayers, TopPlayerEntry
from pipirik_wars.bot.handlers.top import handle_top
from pipirik_wars.bot.presenters.top import REPLY_TOP_EMPTY_RU, REPLY_TOP_HEADER_RU
from pipirik_wars.domain.player import DisplayName, PlayerName, Title


def _msg(*, chat_type: str = "private") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(id=100, is_bot=False, first_name="Алиса", username="alice")
    return msg


def _entry(length: int, *, name: str = "Хвостик", title: Title | None = None) -> TopPlayerEntry:
    return TopPlayerEntry(
        title=title,
        display_name=DisplayName(value=name),
        name=PlayerName(value="X") if name == "_with_player_name" else None,
        length_cm=length,
    )


def _stub_use_case(entries: list[TopPlayerEntry]) -> MagicMock:
    uc = MagicMock(spec=GetTopPlayers)
    uc.execute = AsyncMock(return_value=tuple(entries))
    return uc


@pytest.mark.asyncio
class TestHandleTop:
    async def test_renders_top_in_private_chat(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(100, name="Гигант"), _entry(50, name="Хвостик")])

        await handle_top(cast(Message, msg), cast(GetTopPlayers, uc))

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith(REPLY_TOP_HEADER_RU)
        assert "1. Гигант — 100 см" in sent
        assert "2. Хвостик — 50 см" in sent

    async def test_renders_top_in_group_chat(self) -> None:
        # `/top` доступен и в группах — это социальная команда.
        msg = _msg(chat_type="group")
        uc = _stub_use_case([_entry(7, name="Малыш")])

        await handle_top(cast(Message, msg), cast(GetTopPlayers, uc))

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "Малыш" in sent

    async def test_renders_friendly_empty_message(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([])

        await handle_top(cast(Message, msg), cast(GetTopPlayers, uc))

        msg.answer.assert_awaited_once_with(REPLY_TOP_EMPTY_RU)

    async def test_uses_default_limit_via_execute_no_args(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(1, name="X")])

        await handle_top(cast(Message, msg), cast(GetTopPlayers, uc))

        # execute() — без аргументов: дефолтный limit=100 берёт сам use-case.
        uc.execute.assert_awaited_once_with()
