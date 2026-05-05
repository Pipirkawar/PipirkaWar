"""Юнит-тесты `/upgrade`-handler-а и upgrade-callback-handler-ов (Спринт 1.4.A)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.application.progression import (
    ThicknessUpgraded,
    UpgradeThickness,
)
from pipirik_wars.bot.handlers.upgrade import (
    REPLY_GROUP_RU,
    REPLY_NOT_REGISTERED_RU,
    REPLY_OTHER_RU,
    TOAST_CANCELLED,
    TOAST_INSUFFICIENT,
    TOAST_PLAYER_NOT_FOUND,
    TOAST_RACE,
    TOAST_UPGRADED,
    handle_upgrade,
    handle_upgrade_callback,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.bot.presenters.upgrade import upgrade_callback_data
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.progression import InsufficientLengthError
from pipirik_wars.shared.errors import ConcurrencyError
from tests.fakes import FakeBalanceConfig
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


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


def _player(*, length_cm: int = 5_000, thickness_level: int = 1) -> Player:
    return Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _profile_view(*, length_cm: int = 5_000, thickness_level: int = 1) -> ProfileView:
    return ProfileView(
        player=_player(length_cm=length_cm, thickness_level=thickness_level),
        display_name=DisplayName(value="Пипирик"),
    )


def _stub_profile(view: ProfileView | None = None) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(return_value=view if view is not None else _profile_view())
    return use_case


def _stub_balance() -> IBalanceConfig:
    return FakeBalanceConfig(build_valid_balance())


@pytest.mark.asyncio
class TestHandleUpgrade:
    async def test_private_success_shows_proposal_with_keyboard(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(length_cm=5_000, thickness_level=1))

        await handle_upgrade(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        get_profile.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        # Текст содержит «Прокачка», текущий и целевой уровень, стоимость 4000.
        sent_text = msg.answer.await_args.args[0]
        assert "Прокачка толщины" in sent_text
        assert "Текущий уровень: 1" in sent_text
        assert "Целевой уровень: 2" in sent_text
        assert "4000 см" in sent_text
        # Клавиатура передана; на ней есть кнопка «Подтвердить (4000 см)».
        kwargs = msg.answer.await_args.kwargs
        assert "reply_markup" in kwargs
        kb = kwargs["reply_markup"]
        confirm_btn = kb.inline_keyboard[0][0]
        assert "Подтвердить" in confirm_btn.text
        assert "4000" in confirm_btn.text
        assert confirm_btn.callback_data == "upgrade:confirm:4000"
        cancel_btn = kb.inline_keyboard[0][1]
        assert cancel_btn.text == "Отменить"
        assert cancel_btn.callback_data == "upgrade:cancel:0"

    async def test_player_not_found(self) -> None:
        msg = _msg("private")
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)

        await handle_upgrade(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        msg.answer.assert_awaited_once_with(REPLY_NOT_REGISTERED_RU)

    async def test_insufficient_length_shows_explainer(self) -> None:
        msg = _msg("private")
        # length=4019 → cost=4000, остаток 19 < 20 → отказ.
        get_profile = _stub_profile(_profile_view(length_cm=4_019, thickness_level=1))

        await handle_upgrade(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert "Недостаточно длины" in sent_text
        assert "4000 см" in sent_text
        # Клавиатуры быть не должно — только текст.
        kwargs = msg.answer.await_args.kwargs
        assert "reply_markup" not in kwargs or kwargs["reply_markup"] is None

    async def test_group_replies_instructions(self) -> None:
        msg = _msg("group")
        get_profile = _stub_profile()

        await handle_upgrade(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_supergroup_replies_instructions(self) -> None:
        msg = _msg("supergroup")
        get_profile = _stub_profile()

        await handle_upgrade(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        msg.answer.assert_awaited_once_with(REPLY_GROUP_RU)

    async def test_channel_replies_other(self) -> None:
        msg = _msg("channel")
        get_profile = _stub_profile()

        await handle_upgrade(
            cast(Message, msg),
            _identity("channel"),
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)

    async def test_no_identity_falls_back(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile()

        await handle_upgrade(
            cast(Message, msg),
            None,
            cast(GetProfile, get_profile),
            _stub_balance(),
        )

        msg.answer.assert_awaited_once_with(REPLY_OTHER_RU)
        get_profile.execute.assert_not_awaited()


def _callback(
    *,
    data: str | None,
    tg_user_id: int = 100,
    has_message: bool = True,
) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    if has_message:
        msg = MagicMock()
        msg.chat = Chat(id=42, type="private")
        msg.edit_reply_markup = AsyncMock()
        msg.edit_text = AsyncMock()
        cb.message = msg
    else:
        cb.message = None
    return cb


def _stub_upgrade(
    *,
    success: bool = True,
    error: BaseException | None = None,
    new_thickness: int = 2,
    cost_cm: int = 4_000,
    new_length_cm: int = 1_000,
) -> MagicMock:
    use_case = MagicMock(spec=UpgradeThickness)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    if success:
        before = _player(length_cm=new_length_cm + cost_cm, thickness_level=new_thickness - 1)
        after = _player(length_cm=new_length_cm, thickness_level=new_thickness)
        use_case.execute = AsyncMock(
            return_value=ThicknessUpgraded(
                player_before=before,
                player_after=after,
                cost_cm=cost_cm,
                new_thickness=new_thickness,
            )
        )
    return use_case


@pytest.mark.asyncio
class TestHandleUpgradeCallback:
    async def test_confirm_calls_use_case_and_replaces_text(self) -> None:
        cb = _callback(data="upgrade:confirm:4000")
        upgrade = _stub_upgrade(new_thickness=2, cost_cm=4_000, new_length_cm=1_000)

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_awaited_once()
        passed = upgrade.execute.await_args.args[0]
        assert passed.tg_id == 100
        assert passed.expected_cost_cm == 4_000
        cb.answer.assert_awaited_once_with(TOAST_UPGRADED, show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.message.edit_text.assert_awaited_once()
        sent_text = cb.message.edit_text.await_args.args[0]
        assert "Толщина прокачана до 2" in sent_text
        assert "1000 см" in sent_text

    async def test_cancel_strips_keyboard_and_replaces_text(self) -> None:
        cb = _callback(data="upgrade:cancel:0")
        upgrade = _stub_upgrade()

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_not_awaited()
        cb.answer.assert_awaited_once_with(TOAST_CANCELLED, show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.message.edit_text.assert_awaited_once()
        assert "отменена" in cb.message.edit_text.await_args.args[0].lower()

    async def test_invalid_callback_data_strips_keyboard(self) -> None:
        cb = _callback(data="upgrade:bad")
        upgrade = _stub_upgrade()

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_not_awaited()
        cb.answer.assert_awaited_once_with(TOAST_RACE, show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_player_not_found_shows_alert(self) -> None:
        cb = _callback(data="upgrade:confirm:4000")
        upgrade = _stub_upgrade(error=PlayerNotFoundError(tg_id=100))

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        cb.answer.assert_awaited_once_with(TOAST_PLAYER_NOT_FOUND, show_alert=True)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_insufficient_length_shows_explainer(self) -> None:
        cb = _callback(data="upgrade:confirm:4000")
        err = InsufficientLengthError(
            length_cm=10,
            cost_cm=4_000,
            min_after_spend_cm=20,
            action="thickness_upgrade",
        )
        upgrade = _stub_upgrade(error=err)

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        cb.answer.assert_awaited_once_with(TOAST_INSUFFICIENT, show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.message.edit_text.assert_awaited_once()
        sent_text = cb.message.edit_text.await_args.args[0]
        assert "Недостаточно длины" in sent_text
        assert "4000 см" in sent_text

    async def test_concurrency_error_shows_race_message(self) -> None:
        cb = _callback(data="upgrade:confirm:3000")
        upgrade = _stub_upgrade(error=ConcurrencyError("expected_cost_cm=3000 != actual=4000"))

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        cb.answer.assert_awaited_once_with(TOAST_RACE, show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.message.edit_text.assert_awaited_once()
        assert "Стоимость" in cb.message.edit_text.await_args.args[0]

    async def test_no_identity_silently_returns(self) -> None:
        cb = _callback(data="upgrade:confirm:4000")
        upgrade = _stub_upgrade()

        await handle_upgrade_callback(cb, None, cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_no_message_silently_returns(self) -> None:
        cb = _callback(data="upgrade:confirm:4000", has_message=False)
        upgrade = _stub_upgrade()

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()


@pytest.mark.asyncio
class TestUpgradeCallbackHelperEncoding:
    """Гарантия совместимости handler ↔ presenter callback_data."""

    async def test_round_trip_via_presenter(self) -> None:
        # Презентер генерирует callback_data, handler парсит его.
        cb = _callback(data=upgrade_callback_data("confirm", 9_000))
        upgrade = _stub_upgrade(new_thickness=3, cost_cm=9_000, new_length_cm=500)

        await handle_upgrade_callback(cb, _identity("private"), cast(UpgradeThickness, upgrade))

        upgrade.execute.assert_awaited_once()
        passed = upgrade.execute.await_args.args[0]
        assert passed.expected_cost_cm == 9_000
