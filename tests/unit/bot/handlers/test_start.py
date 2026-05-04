"""Юнит-тесты `/start` handler-а (acceptance 1.1.1, 1.1.3).

Покрывает:
1. ЛС → handler зовёт `RegisterPlayer.execute(...)` и шлёт текст
   успешной регистрации.
2. Повторный `/start` → `PlayerAlreadyRegisteredError` ловится handler-ом
   и шлётся «вы уже зарегистрированы».
3. Группа/супергруппа → handler шлёт текст-инструкцию (НЕ дёргает
   `RegisterPlayer`).
4. Прочие типы (channel, неизвестный) → нейтральное сообщение.
5. ЛС без `tg_identity` → fallback-сообщение, регистрация не зовётся.
6. Username из `message.from_user` пробрасывается в DTO.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.player import RegisterPlayer
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


def _build_message_mock(
    chat_type: str = "private",
    *,
    username: str | None = None,
) -> MagicMock:
    """Возвращает «duck-typed» Message для подачи в handler.

    Возвращаем `MagicMock`, а не `Message`, чтобы mypy не ругался на
    `assert_awaited_once_with(...)`; в `handle_start(...)` кастуем
    обратно в `Message`. Runtime-поведение идентично, т.к. handler
    обращается только к `message.chat.type`, `message.from_user.username`
    и `message.answer(...)`.
    """
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


def _stub_register_player() -> MagicMock:
    use_case = MagicMock(spec=RegisterPlayer)
    fake_player = Player(
        id=1,
        tg_id=100,
        username=None,
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    use_case.execute = AsyncMock(return_value=fake_player)
    return use_case


@pytest.mark.asyncio
class TestHandleStart:
    async def test_private_calls_register_player_and_replies_success(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(RegisterPlayer, register_player),
        )

        register_player.execute.assert_awaited_once()
        actual_input = register_player.execute.await_args.args[0]
        assert isinstance(actual_input, RegisterPlayerInput)
        assert actual_input.tg_id == 100
        assert actual_input.username == "alice"
        msg.answer.assert_awaited_once_with(REPLY_REGISTERED_RU)

    async def test_private_already_registered_replies_already(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player()
        register_player.execute = AsyncMock(
            side_effect=PlayerAlreadyRegisteredError(tg_id=100),
        )

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
        )

        msg.answer.assert_awaited_once_with(REPLY_ALREADY_RU)

    async def test_group_skips_registration_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("group"),
            cast(RegisterPlayer, register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_supergroup_skips_registration(self) -> None:
        msg = _build_message_mock("supergroup")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("supergroup"),
            cast(RegisterPlayer, register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("channel"),
            cast(RegisterPlayer, register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_private_without_identity_replies_other(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            None,
            cast(RegisterPlayer, register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_no_identity_falls_back_to_message_chat_type(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            None,
            cast(RegisterPlayer, register_player),
        )

        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_username_none_when_no_from_user(self) -> None:
        msg = _build_message_mock("private", username=None)
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            cast(RegisterPlayer, register_player),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.username is None
