"""Юнит-тесты `/lang` handler-а (Спринт 1.5.F, ПД 1.5.2).

Покрываем:
1. `/lang ru` в ЛС → `SetPlayerLocale.execute(..., Locale("ru"))` и
   ответ-подтверждение в RU (через ключ `lang-set-ru`).
2. `/lang en` в ЛС → use-case вызывается с `Locale("en")` и ответ —
   в EN.
3. `/lang` без аргументов → ключ `lang-usage`, use-case НЕ вызывается.
4. `/lang fr` (не из SUPPORTED_LOCALES) → ключ `lang-unsupported`
   с параметром `code=fr`, use-case НЕ вызывается.
5. Игрок не зарегистрирован (PlayerNotFoundError) → ключ
   `lang-not-registered`. Use-case вызывается, но в нём бросается.
6. Группа/супергруппа → ключ `lang-group`, use-case НЕ вызывается.
7. Прочие чаты (channel) → ключ `lang-other`, use-case НЕ вызывается.
8. ЛС без `tg_identity` → ключ `lang-other` (fallback).
9. Без локали в data — fallback на `DEFAULT_LOCALE` (en) для текстов
   до подтверждения.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import (
    SetPlayerLocale,
    SetPlayerLocaleResult,
)
from pipirik_wars.bot.handlers.lang import handle_lang
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from tests.fakes import FakeMessageBundle


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


def _command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="lang", args=args)


def _player_after(locale_override: str) -> Player:
    from datetime import UTC, datetime  # noqa: PLC0415

    return Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=20),
        thickness=Thickness(level=1),
        title=Title.NEWBIE,
        name=PlayerName(value="Боб"),
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
        locale_override=locale_override,
    )


def _stub_set_locale(*, raises: Exception | None = None) -> MagicMock:
    use_case = MagicMock(spec=SetPlayerLocale)
    if raises is not None:
        use_case.execute = AsyncMock(side_effect=raises)
        return use_case
    use_case.execute = AsyncMock(
        return_value=SetPlayerLocaleResult(
            player=_player_after("ru"),
            previous_locale_override=None,
            locale_override="ru",
        ),
    )
    return use_case


@pytest.mark.asyncio
class TestHandleLang:
    async def test_lang_ru_in_private_sets_and_confirms_in_ru(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("ru"),
            _identity("private", tg_user_id=100),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_awaited_once_with(
            tg_id=100,
            locale=Locale("ru"),
        )
        msg.answer.assert_awaited_once_with("ru:lang-set-ru")

    async def test_lang_en_in_private_sets_and_confirms_in_en(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("en"),
            _identity("private", tg_user_id=100),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("ru"),
        )

        set_locale.execute.assert_awaited_once_with(
            tg_id=100,
            locale=Locale("en"),
        )
        msg.answer.assert_awaited_once_with("en:lang-set-en")

    async def test_lang_no_args_replies_usage(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command(None),
            _identity("private"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("ru"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:lang-usage")

    async def test_lang_blank_args_replies_usage(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("   "),
            _identity("private"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:lang-usage")

    async def test_lang_unsupported_replies_unsupported(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("fr"),
            _identity("private"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:lang-unsupported[code=fr]")

    async def test_lang_unsupported_case_insensitive(self) -> None:
        """`/lang RU` нормализуется в lowercase."""
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("RU"),
            _identity("private", tg_user_id=100),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_awaited_once_with(
            tg_id=100,
            locale=Locale("ru"),
        )

    async def test_lang_unregistered_player_shows_instruction(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale(raises=PlayerNotFoundError(tg_id=100))
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("ru"),
            _identity("private"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with("en:lang-not-registered")

    async def test_lang_in_group_skips_use_case(self) -> None:
        msg = _build_message_mock("group")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("ru"),
            _identity("group"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("ru"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:lang-group")

    async def test_lang_in_supergroup_skips_use_case(self) -> None:
        msg = _build_message_mock("supergroup")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("en"),
            _identity("supergroup"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("ru"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:lang-group")

    async def test_lang_in_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command("en"),
            _identity("channel"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            Locale("en"),
        )

        set_locale.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:lang-other")

    async def test_lang_no_locale_uses_default(self) -> None:
        msg = _build_message_mock("private")
        set_locale = _stub_set_locale()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_lang(
            cast(Message, msg),
            _command(None),
            _identity("private"),
            cast(SetPlayerLocale, set_locale),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:lang-usage")
