"""Юнит-тесты `/clantop`-handler-а (Спринт 2.2.A / ПД 2.2.1).

С 1.5.* handler рендерит ответ через `ClanTopPresenter` + `IMessageBundle`,
поэтому тесты используют маркерный `FakeMessageBundle`, чтобы проверить
конкретные ключи (`clantop-empty`, `clantop-header`, `clantop-entry`).
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.top import ClanTopEntry, GetTopClans
from pipirik_wars.bot.handlers.clantop import handle_clantop
from pipirik_wars.domain.clan import ClanTitle
from tests.fakes import FakeMessageBundle


def _msg(*, chat_type: str = "private") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(id=100, is_bot=False, first_name="Алиса", username="alice")
    return msg


def _entry(*, clan_id: int, total: int, members: int = 3, title: str = "Каравасы") -> ClanTopEntry:
    return ClanTopEntry(
        clan_id=clan_id,
        clan_title=ClanTitle(title),
        total_length_cm=total,
        member_count=members,
    )


def _stub_use_case(entries: list[ClanTopEntry]) -> MagicMock:
    uc = MagicMock(spec=GetTopClans)
    uc.execute = AsyncMock(return_value=tuple(entries))
    return uc


@pytest.mark.asyncio
class TestHandleClantop:
    async def test_renders_top_in_private_chat(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case(
            [
                _entry(clan_id=1, total=300, title="Львы"),
                _entry(clan_id=2, total=150, title="Орлы"),
            ],
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:clantop-header")
        # Два ряда → два «clantop-entry» с rank=1 и rank=2.
        assert "rank=1" in sent
        assert "rank=2" in sent
        assert "total_length_cm=300" in sent
        assert "total_length_cm=150" in sent

    async def test_renders_top_in_group_chat(self) -> None:
        # /clantop доступен и в группах — это социальная команда.
        msg = _msg(chat_type="group")
        uc = _stub_use_case([_entry(clan_id=7, total=42, title="Алёшки")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "Алёшки" in sent
        assert "ru:clantop-entry[" in sent

    async def test_renders_friendly_empty_message(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clantop-empty")

    async def test_uses_default_limit_via_execute_no_args(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(clan_id=1, total=1)])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            Locale("ru"),
        )

        # execute() — без аргументов: дефолтный limit=50 берёт сам use-case.
        uc.execute.assert_awaited_once_with()

    async def test_locale_propagates_to_bundle(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([_entry(clan_id=7, total=42, title="Eagles")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:clantop-header")
        assert "en:clantop-entry[" in sent

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        msg = _msg(chat_type="private")
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clantop(
            cast(Message, msg),
            cast(GetTopClans, uc),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:clantop-empty")
