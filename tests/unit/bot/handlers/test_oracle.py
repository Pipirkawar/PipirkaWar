"""Юнит-тесты `/oracle`-handler-а (Спринт 1.4.B)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.oracle import InvokeOracle, OracleInvoked
from pipirik_wars.bot.handlers.oracle import (
    handle_oracle,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.bot.presenters.oracle import (
    REPLY_GROUP_RU,
    REPLY_NOT_REGISTERED_RU,
    REPLY_OTHER_RU,
)
from pipirik_wars.domain.oracle import (
    OracleAlreadyUsedTodayError,
    OracleResult,
    OracleTemplate,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from tests.fakes import FakeClock

_NOW = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)  # 12:00 МСК


def _msg(
    *,
    chat_type: str = "private",
    first_name: str = "Алиса",
    username: str | None = "alice",
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(id=100, is_bot=False, first_name=first_name, username=username)
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _player(length_cm: int = 30) -> Player:
    return Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _stub_invoke(
    *,
    bonus_cm: int = 7,
    template_id: str = "oracle.ru.0001",
    template_text: str = "Сегодня всё хорошо, {user}!",
) -> MagicMock:
    use_case = MagicMock(spec=InvokeOracle)
    template = OracleTemplate(id=template_id, text=template_text)
    before = _player(length_cm=30)
    after = _player(length_cm=30 + bonus_cm)
    use_case.execute = AsyncMock(
        return_value=OracleInvoked(
            result=OracleResult(bonus_cm=bonus_cm, template=template),
            player_before=before,
            player_after=after,
            moscow_date=date(2026, 5, 5),
        )
    )
    return use_case


@pytest.mark.asyncio
class TestHandleOracle:
    async def test_private_success_renders_template_and_bonus(self) -> None:
        msg = _msg(chat_type="private", first_name="Алиса")
        invoke = _stub_invoke(bonus_cm=7, template_text="Сегодня всё хорошо, {user}!")
        clock = FakeClock(_NOW)

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            clock,
        )

        invoke.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "Алиса" in sent
        assert "+7 см" in sent
        assert "37 см" in sent

    async def test_group_chat_redirects_to_pm(self) -> None:
        msg = _msg(chat_type="group")
        invoke = _stub_invoke()

        await handle_oracle(
            cast(Message, msg),
            _identity("group"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_supergroup_chat_redirects_to_pm(self) -> None:
        msg = _msg(chat_type="supergroup")
        invoke = _stub_invoke()

        await handle_oracle(
            cast(Message, msg),
            _identity("supergroup"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_no_identity_uses_other_reply(self) -> None:
        msg = _msg(chat_type="channel")
        invoke = _stub_invoke()

        await handle_oracle(
            cast(Message, msg),
            None,
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_player_not_found(self) -> None:
        msg = _msg(chat_type="private")
        invoke = MagicMock(spec=InvokeOracle)
        invoke.execute = AsyncMock(side_effect=PlayerNotFoundError(tg_id=100))

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        msg.answer.assert_awaited_once_with(REPLY_NOT_REGISTERED_RU)

    async def test_already_used_today_renders_cooldown(self) -> None:
        msg = _msg(chat_type="private")
        invoke = MagicMock(spec=InvokeOracle)
        invoke.execute = AsyncMock(
            side_effect=OracleAlreadyUsedTodayError(
                player_id=1,
                moscow_date=date(2026, 5, 5),
            )
        )

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "уже" in sent.lower()
        assert "00:00" in sent

    async def test_uses_username_when_first_name_missing(self) -> None:
        msg = _msg(chat_type="private", first_name="", username="alice")
        invoke = _stub_invoke(template_text="Привет, {user}!")

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
        )

        sent = msg.answer.await_args.args[0]
        assert "@alice" in sent
