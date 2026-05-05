"""Юнит-тесты `/profile` handler-а (Спринт 1.1.E → 1.5.C, ГДД §2.2).

Покрываем:

1. Регистрированный игрок в ЛС → handler зовёт `GetProfile.execute(...)`
   и шлёт карточку через `ProfilePresenter.card(...)`.
2. Незарегистрированный пользователь в ЛС → handler шлёт текст-инструкцию
   через ключ `profile-not-registered`, use-case **зовётся** (он определяет
   «есть/нет»).
3. Группа/супергруппа → ключ `profile-group`, use-case НЕ зовётся.
4. Прочие чаты (channel) → ключ `profile-other`, use-case НЕ зовётся.
5. ЛС без `tg_identity` → ключ `profile-other` (fallback для аномалии).
6. Локаль из middleware пробрасывается в bundle (RU vs EN дают разные
   маркерные строки от `FakeMessageBundle`).
7. Без локали → fallback на `DEFAULT_LOCALE` (`en`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.profile import handle_profile
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
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once_with(tg_id=100)
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # Маркерный bundle сериализует ключ + параметры — этого достаточно,
        # чтобы тест поймал «handler зовёт profile-card с правильным nick/cm/level».
        assert sent.startswith("ru:profile-card[")
        assert "length_cm=47" in sent
        assert "thickness_level=5" in sent
        # nick собирается с локализованным титулом (`profile-title-newbie`),
        # FakeMessageBundle вернёт «ru:profile-title-newbie» и `_render_full_nick`
        # вставит его на место титула.
        assert "ru:profile-title-newbie" in sent

    async def test_private_unregistered_replies_not_registered(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(found=False)
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with("ru:profile-not-registered")

    async def test_group_skips_use_case_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:profile-group")

    async def test_supergroup_skips_use_case(self) -> None:
        msg = _build_message_mock("supergroup")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:profile-group")

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("channel"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:profile-other")

    async def test_private_without_tg_identity_falls_back_to_other(self) -> None:
        # `tg_identity=None` — теоретически невозможно при правильной DI-цепочке,
        # но handler должен переживать аномалию (а не падать с AttributeError).
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            None,
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:profile-other")

    async def test_locale_propagates_to_bundle(self) -> None:
        # Тот же сценарий, что и `test_private_registered_renders_card`,
        # но в EN — маркерные строки префиксируются «en:» вместо «ru:».
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(GetProfile, get_profile),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:profile-card[")
        assert "en:profile-title-newbie" in sent

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        # `locale=None` (middleware промахнулся) → fallback на DEFAULT_LOCALE
        # (=`Locale("en")`). Это та же гарантия, что и в /start.
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_profile(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:profile-group")
