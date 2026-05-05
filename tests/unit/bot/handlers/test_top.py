"""Юнит-тесты `/top`-handler-а (Спринт 1.4.C → 1.5.C, ПД 1.4.6).

С 1.5.C handler рендерит ответ через `TopPresenter` + `IMessageBundle`,
поэтому тесты используют маркерный `FakeMessageBundle`, чтобы проверить
конкретные ключи (`top-empty`, `top-header`, `top-entry`).
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.top import GetTopPlayers, TopPlayerEntry
from pipirik_wars.bot.handlers.top import handle_top
from pipirik_wars.domain.player import DisplayName, PlayerName, Title
from tests.fakes import FakeMessageBundle


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
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:top-header")
        # Два ряда → два «top-entry» с rank=1 и rank=2.
        assert "rank=1" in sent
        assert "rank=2" in sent
        assert "length_cm=100" in sent
        assert "length_cm=50" in sent

    async def test_renders_top_in_group_chat(self) -> None:
        # `/top` доступен и в группах — это социальная команда.
        msg = _msg(chat_type="group")
        uc = _stub_use_case([_entry(7, name="Малыш")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "Малыш" in sent
        assert "ru:top-entry[" in sent

    async def test_renders_friendly_empty_message(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:top-empty")

    async def test_uses_default_limit_via_execute_no_args(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(1, name="X")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            Locale("ru"),
        )

        # execute() — без аргументов: дефолтный limit=100 берёт сам use-case.
        uc.execute.assert_awaited_once_with()

    async def test_locale_propagates_to_bundle(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(7, name="Малыш")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:top-header")
        assert "en:top-entry[" in sent

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_top(
            cast(Message, msg),
            cast(GetTopPlayers, uc),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:top-empty")
