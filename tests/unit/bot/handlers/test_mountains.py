"""Юнит-тесты `/mountains`-handler-а и mountains-callback-handler-а (Спринт 3.1-E)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.mountains import MountainRunStarted, StartMountainRun
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.mountains import (
    handle_mountains,
    handle_mountains_callback,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.mountains import (
    AlreadyInMountainsError,
    MountainRun,
    MountainRunStatus,
    MountainsRequirementError,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _msg(chat_type: str = "private") -> MagicMock:
    msg = MagicMock(spec=Message)
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


def _profile_view() -> ProfileView:
    p = Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=42),
        thickness=Thickness(level=3),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )
    return ProfileView(player=p, display_name=DisplayName(value="Пипирик"))


def _stub_start(*, success: bool = True, error: BaseException | None = None) -> MagicMock:
    use_case = MagicMock(spec=StartMountainRun)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    if success:
        run = MountainRun(
            id=11,
            player_id=1,
            status=MountainRunStatus.IN_PROGRESS,
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=30),
            finished_at=None,
            branch_name="normal_gain",
            length_delta_cm=5,
            drops=(),
        )
        use_case.execute = AsyncMock(return_value=MountainRunStarted(run=run, cooldown_minutes=30))
    return use_case


def _stub_profile(view: ProfileView | None = None) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(return_value=view if view is not None else _profile_view())
    return use_case


@pytest.mark.asyncio
class TestHandleMountains:
    async def test_private_success_sends_started_message(self) -> None:
        msg = _msg("private")
        start = _stub_start()
        get_profile = _stub_profile()

        await handle_mountains(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(StartMountainRun, start),
            cast(GetProfile, get_profile),
            _bundle(),
            _RU,
        )

        start.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:mountains-started" in sent
        assert "cooldown_minutes=30" in sent
        assert "nick=Пипирик" in sent

    async def test_group_chat_uses_group_key(self) -> None:
        msg = _msg("group")
        await handle_mountains(
            cast(Message, msg),
            _identity("group"),
            cast(StartMountainRun, _stub_start()),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:mountains-group")

    async def test_supergroup_chat_uses_group_key(self) -> None:
        msg = _msg("supergroup")
        await handle_mountains(
            cast(Message, msg),
            _identity("supergroup"),
            cast(StartMountainRun, _stub_start()),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:mountains-group")

    async def test_no_identity_uses_other_key(self) -> None:
        msg = _msg("private")
        await handle_mountains(
            cast(Message, msg),
            None,
            cast(StartMountainRun, _stub_start()),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:mountains-other")

    async def test_player_not_found(self) -> None:
        msg = _msg("private")
        start = _stub_start(error=PlayerNotFoundError(tg_id=100))
        await handle_mountains(
            cast(Message, msg),
            _identity("private"),
            cast(StartMountainRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:mountains-not-registered")

    async def test_already_in_mountains(self) -> None:
        msg = _msg("private")
        start = _stub_start(error=AlreadyInMountainsError(player_id=1))
        await handle_mountains(
            cast(Message, msg),
            _identity("private"),
            cast(StartMountainRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:mountains-already-in")

    async def test_requirement_thickness(self) -> None:
        msg = _msg("private")
        start = _stub_start(
            error=MountainsRequirementError(
                player_id=1, requirement="thickness", required=3, actual=1
            )
        )
        await handle_mountains(
            cast(Message, msg),
            _identity("private"),
            cast(StartMountainRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        sent = msg.answer.await_args.args[0]
        assert "mountains-requirement-thickness" in sent
        assert "required=3" in sent
        assert "actual=1" in sent

    async def test_requirement_length(self) -> None:
        msg = _msg("private")
        start = _stub_start(
            error=MountainsRequirementError(
                player_id=1, requirement="length", required=20, actual=15
            )
        )
        await handle_mountains(
            cast(Message, msg),
            _identity("private"),
            cast(StartMountainRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )
        sent = msg.answer.await_args.args[0]
        assert "mountains-requirement-length" in sent
        assert "required_cm=20" in sent
        assert "actual_cm=15" in sent

    async def test_profile_missing_uses_started_fallback(self) -> None:
        msg = _msg("private")
        start = _stub_start()
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)

        await handle_mountains(
            cast(Message, msg),
            _identity("private"),
            cast(StartMountainRun, start),
            cast(GetProfile, get_profile),
            _bundle(),
            _RU,
        )
        sent = msg.answer.await_args.args[0]
        assert "mountains-started-fallback" in sent
        assert "cooldown_minutes=30" in sent


def _callback(data: str) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.answer = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.edit_reply_markup = AsyncMock()
    cb.message = msg
    return cb


@pytest.mark.asyncio
class TestHandleMountainsCallback:
    async def test_no_identity_does_nothing(self) -> None:
        cb = _callback("mountains:equip_item:11:0")
        await handle_mountains_callback(
            cast(CallbackQuery, cb),
            None,
            _bundle(),
            _RU,
        )
        cb.answer.assert_not_awaited()

    async def test_equip_item_action(self) -> None:
        cb = _callback("mountains:equip_item:11:0")
        await handle_mountains_callback(
            cast(CallbackQuery, cb),
            _identity("private"),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert "mountains-toast-item-equipped-placeholder" in toast
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_drop_item_action(self) -> None:
        cb = _callback("mountains:drop_item:11:1")
        await handle_mountains_callback(
            cast(CallbackQuery, cb),
            _identity("private"),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert "mountains-toast-item-dropped" in toast

    async def test_invalid_callback_data_strips_keyboard(self) -> None:
        cb = _callback("not-a-callback")
        await handle_mountains_callback(
            cast(CallbackQuery, cb),
            _identity("private"),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert "mountains-toast-drop-mismatch" in toast

    async def test_dungeon_callback_routed_to_mountains_handler_is_ignored(self) -> None:
        # Защита от промаха фильтра: dungeon-callback в горный handler →
        # toast-mismatch без edit-keyboard.
        cb = _callback("dungeon:equip_item:11:0")
        await handle_mountains_callback(
            cast(CallbackQuery, cb),
            _identity("private"),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert "mountains-toast-drop-mismatch" in toast
        cb.message.edit_reply_markup.assert_not_awaited()
