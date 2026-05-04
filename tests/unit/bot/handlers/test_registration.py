"""Юнит-тесты handler-ов `bot/handlers/registration.py` (Спринт 1.1.D).

Покрываем все три ветки `my_chat_member`/`chat_member`/`migrate_to`
с использованием заранее построенных DTO-input-ов и моков use-case-ов.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import (
    Chat,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    User,
)

from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    JoinClanResult,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.dto.inputs import (
    FreezeClanInput,
    JoinClanInput,
    MigrateClanChatIdInput,
    RegisterClanInput,
)
from pipirik_wars.bot.handlers.registration import (
    JOIN_NOT_REGISTERED_RU,
    handle_chat_member,
    handle_migrate_to,
    handle_my_chat_member,
)


def _stub(spec: type[object]) -> MagicMock:
    use_case = MagicMock(spec=spec)
    use_case.execute = AsyncMock()
    return use_case


def _bot_mock() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.id = 999_000_000
    bot.send_message = AsyncMock()
    return bot


def _make_chat_member_updated(
    *,
    chat_id: int,
    chat_type: str,
    chat_title: str | None,
    new_status: str,
    user_id: int,
    user_is_bot: bool,
    from_user_id: int | None = 1,
) -> MagicMock:
    """Сборка ChatMemberUpdated-mock для подачи в handler.

    aiogram `ChatMemberUpdated` валидирует поля через pydantic;
    проще обойтись MagicMock со ровно той duck-схемой, которую
    handler использует.
    """
    event = MagicMock(spec=ChatMemberUpdated)
    event.chat = Chat(id=chat_id, type=chat_type, title=chat_title)
    user = User(id=user_id, is_bot=user_is_bot, first_name="X")
    new_member = MagicMock(spec=ChatMemberMember)
    new_member.status = new_status
    new_member.user = user
    event.new_chat_member = new_member
    event.from_user = (
        User(id=from_user_id, is_bot=False, first_name="A") if from_user_id is not None else None
    )
    return event


@pytest.mark.asyncio
class TestHandleMyChatMember:
    async def test_bot_added_to_group_calls_register_clan(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="Pipirik Group",
            new_status="member",
            user_id=bot.id,
            user_is_bot=True,
            from_user_id=42,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        register_clan.execute.assert_awaited_once()
        freeze_clan.execute.assert_not_awaited()
        actual_input = register_clan.execute.await_args.args[0]
        assert isinstance(actual_input, RegisterClanInput)
        assert actual_input.chat_id == -100
        assert actual_input.chat_kind == "group"
        assert actual_input.title == "Pipirik Group"
        assert actual_input.added_by_tg_id == 42

    async def test_bot_added_to_supergroup_uses_supergroup_kind(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=-1001000,
            chat_type="supergroup",
            chat_title="Pipirik Super",
            new_status="administrator",
            user_id=bot.id,
            user_is_bot=True,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        actual_input = register_clan.execute.await_args.args[0]
        assert actual_input.chat_kind == "supergroup"

    async def test_bot_kicked_calls_freeze_clan(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="X",
            new_status="kicked",
            user_id=bot.id,
            user_is_bot=True,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        freeze_clan.execute.assert_awaited_once()
        register_clan.execute.assert_not_awaited()
        actual_input = freeze_clan.execute.await_args.args[0]
        assert isinstance(actual_input, FreezeClanInput)
        assert actual_input.chat_id == -100
        assert actual_input.reason == "bot_status:kicked"

    async def test_bot_left_calls_freeze_clan(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="X",
            new_status="left",
            user_id=bot.id,
            user_is_bot=True,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        freeze_clan.execute.assert_awaited_once()
        register_clan.execute.assert_not_awaited()

    async def test_private_chat_skipped(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=42,
            chat_type="private",
            chat_title=None,
            new_status="member",
            user_id=bot.id,
            user_is_bot=True,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        register_clan.execute.assert_not_awaited()
        freeze_clan.execute.assert_not_awaited()

    async def test_falls_back_to_chat_id_for_title_when_missing(self) -> None:
        bot = _bot_mock()
        register_clan = _stub(RegisterClan)
        freeze_clan = _stub(FreezeClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title=None,
            new_status="member",
            user_id=bot.id,
            user_is_bot=True,
        )

        await handle_my_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(RegisterClan, register_clan),
            cast(FreezeClan, freeze_clan),
        )

        actual_input = register_clan.execute.await_args.args[0]
        assert actual_input.title == "chat -100"


@pytest.mark.asyncio
class TestHandleChatMember:
    async def test_user_joined_and_registered_creates_membership(self) -> None:
        bot = _bot_mock()
        join_clan = _stub(JoinClan)
        join_clan.execute = AsyncMock(
            return_value=JoinClanResult(
                outcome="joined",
                clan=None,
                member=None,
            )
        )
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="Clan",
            new_status="member",
            user_id=42,
            user_is_bot=False,
        )

        await handle_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(JoinClan, join_clan),
        )

        join_clan.execute.assert_awaited_once()
        bot.send_message.assert_not_awaited()
        actual_input = join_clan.execute.await_args.args[0]
        assert isinstance(actual_input, JoinClanInput)
        assert actual_input.chat_id == -100
        assert actual_input.tg_id == 42

    async def test_user_joined_but_not_registered_sends_dm(self) -> None:
        bot = _bot_mock()
        join_clan = _stub(JoinClan)
        join_clan.execute = AsyncMock(
            return_value=JoinClanResult(
                outcome="not_registered",
                clan=None,
                member=None,
            )
        )
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="Clan",
            new_status="member",
            user_id=42,
            user_is_bot=False,
        )

        await handle_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(JoinClan, join_clan),
        )

        bot.send_message.assert_awaited_once_with(
            chat_id=42,
            text=JOIN_NOT_REGISTERED_RU,
        )

    async def test_bot_joining_is_skipped(self) -> None:
        bot = _bot_mock()
        join_clan = _stub(JoinClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="Clan",
            new_status="member",
            user_id=999,
            user_is_bot=True,
        )

        await handle_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(JoinClan, join_clan),
        )

        join_clan.execute.assert_not_awaited()

    async def test_left_status_skipped(self) -> None:
        bot = _bot_mock()
        join_clan = _stub(JoinClan)
        event = _make_chat_member_updated(
            chat_id=-100,
            chat_type="group",
            chat_title="Clan",
            new_status="left",
            user_id=42,
            user_is_bot=False,
        )

        await handle_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(JoinClan, join_clan),
        )

        join_clan.execute.assert_not_awaited()

    async def test_private_chat_skipped(self) -> None:
        bot = _bot_mock()
        join_clan = _stub(JoinClan)
        event = _make_chat_member_updated(
            chat_id=42,
            chat_type="private",
            chat_title=None,
            new_status="member",
            user_id=42,
            user_is_bot=False,
        )

        await handle_chat_member(
            cast(ChatMemberUpdated, event),
            cast(Bot, bot),
            cast(JoinClan, join_clan),
        )

        join_clan.execute.assert_not_awaited()


@pytest.mark.asyncio
class TestHandleMigrateTo:
    async def test_migrate_event_calls_migrate_clan(self) -> None:
        migrate_clan = _stub(MigrateClanChatId)
        msg = MagicMock(spec=Message)
        msg.chat = Chat(id=-100, type="group")
        msg.migrate_to_chat_id = -1001000

        await handle_migrate_to(
            cast(Message, msg),
            cast(MigrateClanChatId, migrate_clan),
        )

        migrate_clan.execute.assert_awaited_once()
        actual_input = migrate_clan.execute.await_args.args[0]
        assert isinstance(actual_input, MigrateClanChatIdInput)
        assert actual_input.old_chat_id == -100
        assert actual_input.new_chat_id == -1001000
        assert actual_input.new_chat_kind == "supergroup"
