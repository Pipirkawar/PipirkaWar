"""Юнит-тесты `/roulette_free`-handler-а и roulette-callback-handler-а
(Спринт 3.5-D).

Handler рендерит ответы через `RoulettePresenter` + `IMessageBundle`, поэтому
тесты используют `FakeMessageBundle` для проверки конкретных
ключей `roulette-free-*` (без привязки к реальному переводу).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.application.roulette import SpinFreeRoulette, SpinResult
from pipirik_wars.bot.handlers.roulette import (
    handle_roulette_callback,
    handle_roulette_free,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
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
from pipirik_wars.domain.roulette import (
    InsufficientLengthForRouletteError,
    RouletteOutcome,
    RouletteOutcomeKind,
    RouletteThicknessGateError,
)
from tests.fakes import FakeBalanceConfig, FakeMessageBundle
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


def _player(*, length_cm: int = 5_000, thickness_level: int = 2) -> Player:
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


def _profile_view(*, length_cm: int = 5_000, thickness_level: int = 2) -> ProfileView:
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


def _bundle() -> IMessageBundle:
    return cast(IMessageBundle, FakeMessageBundle())


@pytest.mark.asyncio
class TestHandleRouletteFree:
    async def test_private_success_shows_prompt_with_keyboard(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(length_cm=5_000, thickness_level=2))

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-free-prompt[")
        assert "current_length_cm=5000" in sent_text
        assert "cost_cm=100" in sent_text
        # Клавиатура: одна кнопка `[Прокрутить — N см]` с invariant callback_data.
        kwargs = msg.answer.await_args.kwargs
        kb = kwargs["reply_markup"]
        (spin_btn,) = kb.inline_keyboard[0]
        assert spin_btn.text == "ru:roulette-free-button-spin[cost_cm=100]"
        assert spin_btn.callback_data == "roulette_free:spin"

    async def test_player_not_found(self) -> None:
        msg = _msg("private")
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-free-not-registered")

    async def test_thickness_gate_blocks(self) -> None:
        msg = _msg("private")
        # thickness=1 < min_thickness_level=2 → отказ.
        get_profile = _stub_profile(_profile_view(length_cm=5_000, thickness_level=1))

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-free-requirement-thickness[")
        assert "required=2" in sent_text
        assert "actual=1" in sent_text
        # Клавиатуры быть не должно — только текст.
        kwargs = msg.answer.await_args.kwargs
        assert "reply_markup" not in kwargs or kwargs["reply_markup"] is None

    async def test_length_gate_blocks(self) -> None:
        msg = _msg("private")
        # length=99 < cost_cm=100 → отказ.
        get_profile = _stub_profile(_profile_view(length_cm=99, thickness_level=2))

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-free-requirement-length[")
        assert "required_cm=100" in sent_text
        assert "actual_cm=99" in sent_text
        kwargs = msg.answer.await_args.kwargs
        assert "reply_markup" not in kwargs or kwargs["reply_markup"] is None

    async def test_group_replies_instructions(self) -> None:
        msg = _msg("group")
        get_profile = _stub_profile()

        await handle_roulette_free(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:roulette-free-group")

    async def test_supergroup_replies_instructions(self) -> None:
        msg = _msg("supergroup")
        get_profile = _stub_profile()

        await handle_roulette_free(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-free-group")

    async def test_channel_replies_other(self) -> None:
        msg = _msg("channel")
        get_profile = _stub_profile()

        await handle_roulette_free(
            cast(Message, msg),
            _identity("channel"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-free-other")

    async def test_no_identity_falls_back(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile()

        await handle_roulette_free(
            cast(Message, msg),
            None,
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-free-other")
        get_profile.execute.assert_not_awaited()

    async def test_locale_propagates_to_presenter_en(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(length_cm=5_000, thickness_level=2))

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("en"),
        )

        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("en:roulette-free-prompt[")

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(length_cm=5_000, thickness_level=2))

        await handle_roulette_free(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            None,
        )

        # DEFAULT_LOCALE = "en"
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("en:roulette-free-prompt[")


def _callback(
    *,
    data: str | None,
    tg_user_id: int = 100,
    has_message: bool = True,
    message_id: int = 555,
) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    if has_message:
        msg = MagicMock()
        msg.chat = Chat(id=42, type="private")
        msg.message_id = message_id
        msg.edit_reply_markup = AsyncMock()
        msg.edit_text = AsyncMock()
        cb.message = msg
    else:
        cb.message = None
    return cb


def _stub_spin(
    *,
    result: SpinResult | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SpinFreeRoulette)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    if result is None:
        result = SpinResult(
            outcome=RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42),
            spent_cm=100,
            idempotent=False,
        )
    use_case.execute = AsyncMock(return_value=result)
    return use_case


@pytest.mark.asyncio
class TestHandleRouletteCallback:
    async def test_spin_success_length_outcome(self) -> None:
        cb = _callback(data="roulette_free:spin", message_id=777)
        spin = _stub_spin(
            result=SpinResult(
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42),
                spent_cm=100,
                idempotent=False,
            )
        )

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        spin.execute.assert_awaited_once()
        cmd = spin.execute.await_args.args[0]
        assert cmd.player_id == 100
        assert cmd.idempotency_key == "msg:777"
        cb.answer.assert_awaited_once_with("ru:roulette-free-toast-spin-complete", show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        # 3 кадра анимации + final result-карточка = 4 edit_text-а.
        assert cb.message.edit_text.await_count == 4
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text.startswith("ru:roulette-free-result-length[")
        assert "length_cm=42" in last_text
        assert "cost_cm=100" in last_text

    async def test_spin_success_item_outcome(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(
            result=SpinResult(
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                spent_cm=100,
                idempotent=False,
            )
        )

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text.startswith("ru:roulette-free-result-item[")
        assert "cost_cm=100" in last_text

    async def test_spin_idempotent_repeats_returns_idempotent_card(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(
            result=SpinResult(outcome=None, spent_cm=0, idempotent=True),
        )

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with(
            "ru:roulette-free-toast-already-processed",
            show_alert=False,
        )
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text == "ru:roulette-free-result-idempotent"

    async def test_invalid_callback_data_strips_keyboard_and_toasts(self) -> None:
        cb = _callback(data="roulette_free:bogus")
        spin = _stub_spin()

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        spin.execute.assert_not_awaited()
        cb.answer.assert_awaited_once_with("ru:roulette-free-toast-error", show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_thickness_gate_error_shows_explainer(self) -> None:
        cb = _callback(data="roulette_free:spin")
        err = RouletteThicknessGateError(
            player_id=100,
            thickness_level=1,
            required_level=2,
        )
        spin = _stub_spin(error=err)

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with(
            "ru:roulette-free-toast-thickness-gate[actual=1,required=2]",
            show_alert=True,
        )
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text.startswith("ru:roulette-free-requirement-thickness[")
        assert "required=2" in last_text
        assert "actual=1" in last_text

    async def test_insufficient_length_error_shows_explainer(self) -> None:
        cb = _callback(data="roulette_free:spin")
        err = InsufficientLengthForRouletteError(
            player_id=100,
            length_cm=50,
            cost_cm=100,
        )
        spin = _stub_spin(error=err)

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with(
            "ru:roulette-free-toast-insufficient-length[actual_cm=50,required_cm=100]",
            show_alert=True,
        )
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text.startswith("ru:roulette-free-requirement-length[")
        assert "required_cm=100" in last_text
        assert "actual_cm=50" in last_text

    async def test_player_not_found_shows_alert(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(error=PlayerNotFoundError(tg_id=100))

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with(
            "ru:roulette-free-toast-not-registered",
            show_alert=True,
        )
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text == "ru:roulette-free-not-registered"

    async def test_unexpected_error_shows_toast_only(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(error=RuntimeError("unexpected"))

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with("ru:roulette-free-toast-error", show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_no_identity_silently_returns(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin()

        await handle_roulette_callback(
            cb,
            None,
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        spin.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_no_message_silently_returns(self) -> None:
        cb = _callback(data="roulette_free:spin", has_message=False)
        spin = _stub_spin()

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        spin.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_no_data_silently_returns(self) -> None:
        cb = _callback(data=None)
        spin = _stub_spin()

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        spin.execute.assert_not_awaited()
        cb.answer.assert_not_awaited()

    async def test_locale_propagates_en(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(
            result=SpinResult(outcome=None, spent_cm=0, idempotent=True),
        )

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("en"),
            frame_delay_s=0.0,
        )

        cb.answer.assert_awaited_once_with(
            "en:roulette-free-toast-already-processed",
            show_alert=False,
        )
        last_text = cb.message.edit_text.await_args.args[0]
        assert last_text == "en:roulette-free-result-idempotent"

    async def test_no_locale_falls_back_to_default(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin(
            result=SpinResult(outcome=None, spent_cm=0, idempotent=True),
        )

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            None,
            frame_delay_s=0.0,
        )

        # DEFAULT_LOCALE = "en"
        cb.answer.assert_awaited_once_with(
            "en:roulette-free-toast-already-processed",
            show_alert=False,
        )

    async def test_animation_renders_3_frames_before_result(self) -> None:
        cb = _callback(data="roulette_free:spin")
        spin = _stub_spin()

        await handle_roulette_callback(
            cb,
            _identity("private"),
            cast(SpinFreeRoulette, spin),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
            frame_delay_s=0.0,
        )

        # 3 кадра анимации + 1 финальный = 4 вызова edit_text.
        assert cb.message.edit_text.await_count == 4
        # Первые три текста — анимационные кадры.
        frame1 = cb.message.edit_text.await_args_list[0].args[0]
        frame2 = cb.message.edit_text.await_args_list[1].args[0]
        frame3 = cb.message.edit_text.await_args_list[2].args[0]
        assert frame1 == "ru:roulette-free-animation-frame-1"
        assert frame2 == "ru:roulette-free-animation-frame-2"
        assert frame3 == "ru:roulette-free-animation-frame-3"
