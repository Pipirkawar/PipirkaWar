"""Юнит-тесты `/start` handler-а (acceptance 1.1.1, 1.1.3, 1.2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.bot.handlers.start import (
    REPLY_ALREADY_RU,
    REPLY_GROUP_RU,
    REPLY_OTHER_RU,
    REPLY_REGISTERED_RU,
    handle_start,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import (
    Player,
    PlayerAlreadyRegisteredError,
    PlayerStatus,
)
from pipirik_wars.domain.player.value_objects import Length, Thickness
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
    SignupQueueEntry,
)
from tests.fakes import FakeSignupQueueRepository


def _build_message_mock(
    chat_type: str = "private",
    *,
    username: str | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    if username is None:
        msg.from_user = None
    else:
        msg.from_user = MagicMock()
        msg.from_user.username = username
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _player(tg_id: int = 100) -> Player:
    return Player(
        id=1,
        tg_id=tg_id,
        username=None,
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )


def _stub_register_player(
    *,
    return_value: PlayerRegistered | PlayerQueued | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=RegisterPlayer)
    if side_effect is not None:
        use_case.execute = AsyncMock(side_effect=side_effect)
    else:
        use_case.execute = AsyncMock(
            return_value=return_value or PlayerRegistered(player=_player()),
        )
    return use_case


def _queue() -> FakeSignupQueueRepository:
    return FakeSignupQueueRepository()


@pytest.mark.asyncio
class TestHandleStart:
    async def test_private_calls_register_player_and_replies_success(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        register_player.execute.assert_awaited_once()
        actual_input = register_player.execute.await_args.args[0]
        assert isinstance(actual_input, RegisterPlayerInput)
        assert actual_input.tg_id == 100
        assert actual_input.username == "alice"
        msg.answer.assert_awaited_once_with(REPLY_REGISTERED_RU)

    async def test_private_already_registered_replies_already(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player(
            side_effect=PlayerAlreadyRegisteredError(tg_id=100),
        )
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        msg.answer.assert_awaited_once_with(REPLY_ALREADY_RU)

    async def test_private_queued_replies_with_position(self) -> None:
        msg = _build_message_mock("private", username="bob")
        entry = SignupQueueEntry(
            id=7,
            tg_id=100,
            username="bob",
            locale="ru",
            position=42,
            enqueued_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        register_player = _stub_register_player(return_value=PlayerQueued(entry=entry))
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert "Серверы переполнены" in sent_text
        assert "#42" in sent_text

    async def test_private_already_queued_reads_current_position_and_replies(
        self,
    ) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player(
            side_effect=AlreadyQueuedError(tg_id=100),
        )
        queue = _queue()
        await queue.enqueue(
            entry=SignupQueueEntry(
                id=None,
                tg_id=100,
                username=None,
                locale=None,
                position=0,
                enqueued_at=datetime(2026, 5, 4, tzinfo=UTC),
            )
        )

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert "#1" in sent_text

    async def test_group_skips_registration_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("group"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_supergroup_skips_registration(self) -> None:
        msg = _build_message_mock("supergroup")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("supergroup"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("channel"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_private_without_identity_replies_other(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            None,
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_no_identity_falls_back_to_message_chat_type(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            None,
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_username_none_when_no_from_user(self) -> None:
        msg = _build_message_mock("private", username=None)
        register_player = _stub_register_player()
        queue = _queue()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
            cast(ISignupQueueRepository, queue),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.username is None
