"""Юнит-тесты `/forest`-handler-а и forest-callback-handler-ов (Спринт 1.3.D → 1.5.E)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.forest import (
    ApplyForestNameDrop,
    ForestNameDropApplied,
    ForestRunStarted,
    StartForestRun,
)
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.forest import (
    handle_forest,
    handle_forest_callback,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.forest import (
    AlreadyInForestError,
    ForestDropMismatchError,
    ForestRun,
    ForestRunNotFoundError,
    ForestRunOwnershipError,
    ForestRunStatus,
    NoDrop,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerName,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


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


def _profile_view(name: PlayerName | None = None) -> ProfileView:
    p = Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )
    return ProfileView(player=p, display_name=DisplayName(value="Пипирик"))


def _stub_start(*, success: bool = True, error: BaseException | None = None) -> MagicMock:
    use_case = MagicMock(spec=StartForestRun)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    if success:
        run = ForestRun(
            id=11,
            player_id=1,
            status=ForestRunStatus.IN_PROGRESS,
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=15),
            finished_at=None,
            branch_name="normal",
            length_delta_cm=5,
            drop=NoDrop(),
        )
        use_case.execute = AsyncMock(return_value=ForestRunStarted(run=run, cooldown_minutes=15))
    return use_case


def _stub_profile(view: ProfileView | None = None) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(return_value=view if view is not None else _profile_view())
    return use_case


def _stub_apply_name_drop(
    *,
    was_already: bool = False,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=ApplyForestNameDrop)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    base = _profile_view().player
    use_case.execute = AsyncMock(
        return_value=ForestNameDropApplied(
            player_before=base,
            player_after=base,
            new_name=PlayerName(value="X"),
            was_already_applied=was_already,
        )
    )
    return use_case


@pytest.mark.asyncio
class TestHandleForest:
    async def test_private_success_sends_started_message_with_locale(self) -> None:
        msg = _msg("private")
        start = _stub_start()
        get_profile = _stub_profile()

        await handle_forest(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(StartForestRun, start),
            cast(GetProfile, get_profile),
            _bundle(),
            _RU,
        )

        start.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # FakeMessageBundle: «ru:forest-started[cooldown_minutes=15,nick=Пипирик]»
        assert "ru:forest-started" in sent
        assert "cooldown_minutes=15" in sent
        assert "nick=Пипирик" in sent

    async def test_player_not_found_uses_not_registered_key(self) -> None:
        msg = _msg("private")
        start = _stub_start(error=PlayerNotFoundError(tg_id=100))

        await handle_forest(
            cast(Message, msg),
            _identity("private"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:forest-not-registered")

    async def test_already_in_forest_uses_already_in_key(self) -> None:
        msg = _msg("private")
        start = _stub_start(error=AlreadyInForestError(player_id=1))

        await handle_forest(
            cast(Message, msg),
            _identity("private"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:forest-already-in")

    async def test_group_uses_group_key(self) -> None:
        msg = _msg("group")
        start = _stub_start()

        await handle_forest(
            cast(Message, msg),
            _identity("group"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _EN,
        )

        start.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:forest-group")

    async def test_supergroup_uses_group_key(self) -> None:
        msg = _msg("supergroup")
        start = _stub_start()

        await handle_forest(
            cast(Message, msg),
            _identity("supergroup"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )

        start.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:forest-group")

    async def test_channel_uses_other_key(self) -> None:
        msg = _msg("channel")
        start = _stub_start()

        await handle_forest(
            cast(Message, msg),
            _identity("channel"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:forest-other")

    async def test_private_no_identity_falls_back_to_other(self) -> None:
        msg = _msg("private")
        start = _stub_start()

        await handle_forest(
            cast(Message, msg),
            None,
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:forest-other")
        start.execute.assert_not_awaited()

    async def test_locale_defaults_to_default_locale_when_none(self) -> None:
        msg = _msg("group")
        start = _stub_start()

        await handle_forest(
            cast(Message, msg),
            _identity("group"),
            cast(StartForestRun, start),
            cast(GetProfile, _stub_profile()),
            _bundle(),
            None,
        )

        # DEFAULT_LOCALE = "en"
        msg.answer.assert_awaited_once_with("en:forest-group")

    async def test_profile_missing_after_start_falls_back_to_started_fallback(self) -> None:
        msg = _msg("private")
        start = _stub_start()
        # Профиль вернул None — handler должен прислать минимальный fallback.
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)

        await handle_forest(
            cast(Message, msg),
            _identity("private"),
            cast(StartForestRun, start),
            cast(GetProfile, get_profile),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # Маркер FakeMessageBundle: «ru:forest-started-fallback[cooldown_minutes=15]»
        assert sent == "ru:forest-started-fallback[cooldown_minutes=15]"


def _callback(
    *,
    data: str | None = "forest:apply_name:11",
    tg_user_id: int = 100,
    has_message: bool = True,
) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    if has_message:
        cb.message = MagicMock()
        cb.message.edit_reply_markup = AsyncMock()
        cb.message.chat = Chat(id=42, type="private")
    else:
        cb.message = None
    return cb


@pytest.mark.asyncio
class TestForestCallback:
    async def test_apply_name_success_uses_toast_name_applied(self) -> None:
        cb = _callback(data="forest:apply_name:11")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_awaited_once()
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-name-applied"
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_apply_name_already_applied(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop(was_already=True)

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-name-already-applied"

    async def test_apply_name_run_not_found(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop(error=ForestRunNotFoundError(run_id=11))

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-run-not-found"
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_apply_name_player_not_found(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop(error=PlayerNotFoundError(tg_id=100))

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-player-not-found"
        # При player_not_found клавиатуру не снимаем (юзер не зарегистрирован).
        cb.message.edit_reply_markup.assert_not_awaited()

    async def test_apply_name_ownership_mismatch(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop(
            error=ForestRunOwnershipError(run_id=11, run_player_id=1, actor_player_id=2)
        )

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-foreign-button"
        cb.message.edit_reply_markup.assert_not_awaited()

    async def test_apply_name_drop_mismatch(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop(
            error=ForestDropMismatchError(run_id=11, expected="name", got="ItemDrop")
        )

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-drop-mismatch"
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_drop_name_no_use_case_call(self) -> None:
        cb = _callback(data="forest:drop_name:11")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-name-dropped"
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_equip_item_action(self) -> None:
        cb = _callback(data="forest:equip_item:11")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-item-equipped-placeholder"

    async def test_drop_item_action(self) -> None:
        cb = _callback(data="forest:drop_item:11")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-item-dropped"

    async def test_invalid_callback_data_silenced_with_drop_mismatch_toast(self) -> None:
        cb = _callback(data="not:forest:data")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:forest-toast-drop-mismatch"

    async def test_no_identity_returns_silently(self) -> None:
        cb = _callback()
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            None,
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )

        use_case.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_strip_keyboard_swallows_edit_error(self) -> None:
        cb = _callback()
        cb.message.edit_reply_markup = AsyncMock(side_effect=RuntimeError("too old"))
        use_case = _stub_apply_name_drop()

        # Не должно бросить — `_strip_keyboard` поглощает любые ошибки.
        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()

    async def test_locale_defaults_when_none(self) -> None:
        cb = _callback(data="forest:drop_item:11")
        use_case = _stub_apply_name_drop()

        await handle_forest_callback(
            cb,
            _identity(),
            cast(ApplyForestNameDrop, use_case),
            _bundle(),
            None,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "en:forest-toast-item-dropped"
