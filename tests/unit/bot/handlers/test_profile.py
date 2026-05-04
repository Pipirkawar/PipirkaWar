"""Юнит-тесты `/profile` handler-а (Спринт 1.1.E, ГДД §2.2).

Покрываем:

1. Регистрированный игрок в ЛС → handler зовёт `GetProfile.execute(...)`
   и шлёт карточку через `render_profile_card(...)`.
2. Незарегистрированный пользователь в ЛС → handler шлёт текст-инструкцию
   «нажми /start», use-case **зовётся** (он определяет «есть/нет»).
3. Группа/супергруппа → handler шлёт инструкцию, use-case НЕ зовётся.
4. Прочие чаты (channel) → нейтральное сообщение, use-case НЕ зовётся.
5. ЛС без `tg_identity` → fallback-сообщение, use-case НЕ зовётся.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.profile import (
    REPLY_GROUP_RU,
    REPLY_NOT_REGISTERED_RU,
    REPLY_OTHER_RU,
    handle_profile,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import (
    DisplayName,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username


def _build_message_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _stub_get_profile(
    *,
    found: bool = True,
    title: Title | None = Title.NEWBIE,
    name: PlayerName | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    if not found:
        use_case.execute = AsyncMock(return_value=None)
        return use_case
    fake_player = Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=47),
        thickness=Thickness(level=5),
        title=title,
        name=name if name is not None else PlayerName(value="Коляндр"),
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    use_case.execute = AsyncMock(
        return_value=ProfileView(
            player=fake_player,
            display_name=DisplayName(value="Бананчик"),
        ),
    )
    return use_case


@pytest.mark.asyncio
class TestHandleProfile:
    async def test_private_registered_renders_card(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()

        await handle_profile(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(GetProfile, get_profile),
        )

        get_profile.execute.assert_awaited_once_with(tg_id=100)
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # Acceptance §2.1: «Титул Название Имя» в первой строке.
        assert "Новичок Бананчик Коляндр" in sent
        assert "📏" in sent
        assert "Толщина: 5" in sent

    async def test_private_unregistered_replies_not_registered(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(found=False)

        await handle_profile(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
        )

        # Use-case должен был быть зван — это его дело сообщить «нет».
        get_profile.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with(REPLY_NOT_REGISTERED_RU)

    async def test_group_skips_use_case_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()

        await handle_profile(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_supergroup_skips_use_case(self) -> None:
        msg = _build_message_mock("supergroup")
        get_profile = _stub_get_profile()

        await handle_profile(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetProfile, get_profile),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        get_profile = _stub_get_profile()

        await handle_profile(
            cast(Message, msg),
            _identity("channel"),
            cast(GetProfile, get_profile),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_no_identity_replies_other(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()

        await handle_profile(
            cast(Message, msg),
            None,
            cast(GetProfile, get_profile),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)
