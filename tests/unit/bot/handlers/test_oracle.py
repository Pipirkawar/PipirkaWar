"""Юнит-тесты `/oracle`-handler-а (Спринт 1.4.B → 1.5.D).

С 1.5.D handler рендерит ответы через `OraclePresenter` + `IMessageBundle`,
поэтому тесты используют `FakeMessageBundle` для проверки конкретных
ключей `oracle-*` (без привязки к реальному переводу).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.oracle import InvokeOracle, OracleInvoked
from pipirik_wars.bot.handlers.oracle import handle_oracle
from pipirik_wars.bot.middlewares.auth import TgIdentity
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
from tests.fakes import FakeClock, FakeMessageBundle

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
            base_cm=bonus_cm,
            tribe_bonus_cm=0,
            n_active_tribes=0,
        )
    )
    return use_case


@pytest.mark.asyncio
class TestHandleOracle:
    async def test_private_success_renders_template_and_bonus(self) -> None:
        msg = _msg(chat_type="private", first_name="Алиса")
        invoke = _stub_invoke(bonus_cm=7, template_text="Сегодня всё хорошо, {user}!")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        invoke.execute.assert_awaited_once()
        # Use-case получает локаль игрока (RU здесь).
        call_input = invoke.execute.await_args.args[0]
        assert call_input.locale == "ru"
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # FakeMessageBundle сериализует ключ + параметры → детерминированно.
        assert sent.startswith("ru:oracle-success[")
        assert "prediction=Сегодня всё хорошо, Алиса!" in sent
        assert "bonus_cm=7" in sent
        assert "new_length_cm=37" in sent

    async def test_group_chat_redirects_to_pm(self) -> None:
        msg = _msg(chat_type="group")
        invoke = _stub_invoke()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("group"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with("ru:oracle-group")

    async def test_supergroup_chat_redirects_to_pm(self) -> None:
        msg = _msg(chat_type="supergroup")
        invoke = _stub_invoke()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("supergroup"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with("ru:oracle-group")

    async def test_no_identity_uses_other_reply(self) -> None:
        msg = _msg(chat_type="channel")
        invoke = _stub_invoke()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            None,
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        invoke.execute.assert_not_called()
        msg.answer.assert_awaited_once_with("ru:oracle-other")

    async def test_player_not_found(self) -> None:
        msg = _msg(chat_type="private")
        invoke = MagicMock(spec=InvokeOracle)
        invoke.execute = AsyncMock(side_effect=PlayerNotFoundError(tg_id=100))
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:oracle-not-registered")

    async def test_already_used_today_renders_cooldown(self) -> None:
        msg = _msg(chat_type="private")
        invoke = MagicMock(spec=InvokeOracle)
        invoke.execute = AsyncMock(
            side_effect=OracleAlreadyUsedTodayError(
                player_id=1,
                moscow_date=date(2026, 5, 5),
            )
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:oracle-already-used[")
        # 12:00 МСК → 12 часов до 00:00 МСК.
        assert "hours=12" in sent
        assert "minutes=00" in sent

    async def test_uses_username_when_first_name_missing(self) -> None:
        msg = _msg(chat_type="private", first_name="", username="alice")
        invoke = _stub_invoke(template_text="Привет, {user}!")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("ru"),
        )

        sent = msg.answer.await_args.args[0]
        assert "prediction=Привет, @alice!" in sent

    async def test_locale_propagates_to_use_case_and_bundle(self) -> None:
        # EN-локаль уходит и в use-case (для выбора каталога предсказаний),
        # и в presenter (для текста ответа).
        msg = _msg(chat_type="private", first_name="Alice")
        invoke = _stub_invoke(template_text="Today is great, {user}!")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            Locale("en"),
        )

        call_input = invoke.execute.await_args.args[0]
        assert call_input.locale == "en"
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:oracle-success[")

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        # Если middleware не пробросил локаль — DEFAULT_LOCALE = "en".
        msg = _msg(chat_type="private", first_name="Alice")
        invoke = _stub_invoke(template_text="Hi, {user}!")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_oracle(
            cast(Message, msg),
            _identity("private"),
            cast(InvokeOracle, invoke),
            FakeClock(_NOW),
            bundle,
            None,
        )

        call_input = invoke.execute.await_args.args[0]
        assert call_input.locale == "en"
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:oracle-success[")
