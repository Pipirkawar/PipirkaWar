"""Юнит-тесты `/clan_head`-handler-а (Спринт 2.3.E / ПД 2.3.4-5).

Покрываем все ветки handler-а:
* `tg_identity is None` → тихий no-op (без ответа);
* в ЛС / не в групповом чате → `clan-head-needs-group-chat`;
* в групповом чате, не привязанном к клану (или `clan.id is None`)
  → `clan-head-not-registered`;
* `ClanFrozenError` от use-case-а → `clan-head-frozen-clan`;
* `DailyHeadInsufficientActivityError` → `clan-head-not-enough-active`
  с `active_count` и `required` в плейсхолдерах;
* успех + `was_new=True` → `clan-head-success` с цитатой и
  подставленным `head_display_name`;
* идемпотентный возврат + `was_new=False` → `clan-head-already-assigned`;
* пустой каталог цитат → fallback `_FALLBACK_QUOTE` (`👑`);
* `{user}`-плейсхолдер в шаблоне цитаты подставляется на имя главы;
* `locale=None` → fallback на `DEFAULT_LOCALE`;
* `Player.username is None` → display = `"глава"` (последний fallback).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.daily_head import (
    IClanQuoteTemplateProvider,
    RequestDailyHead,
)
from pipirik_wars.application.daily_head.dto import DailyHeadResolved
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.handlers.clan_head import handle_clan_head
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanFrozenError,
    ClanStatus,
    ClanTitle,
    IClanRepository,
)
from pipirik_wars.domain.daily_head import (
    ClanQuoteTemplate,
    DailyHeadAssignment,
    DailyHeadInsufficientActivityError,
    DailyHeadSource,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.shared.ports import IRandom
from tests.fakes import FakeClanQuoteTemplateProvider, FakeMessageBundle, FakeRandom

_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
_MOSCOW_TODAY = date(2026, 5, 5)


def _msg(*, chat_type: str = "supergroup", chat_id: int = -100100) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(id=100, is_bot=False, first_name="Алиса", username="alice")
    return msg


def _identity(*, chat_kind: str = "supergroup", chat_id: int = -100100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=100,
        chat_id=chat_id,
        chat_kind=chat_kind,
        language_code=None,
    )


def _clan(
    *,
    clan_id: int | None = 5,
    chat_id: int = -100100,
    title: str = "Лесные",
) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=title),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _player(*, player_id: int = 11, username: str | None = "alice") -> Player:
    return Player(
        id=player_id,
        tg_id=100 + player_id,
        username=Username(value=username) if username else None,
        length=Length(cm=120),
        thickness=Thickness(level=2),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _assignment(*, bonus_cm: int = 15, player_id: int = 11) -> DailyHeadAssignment:
    return DailyHeadAssignment(
        id=42,
        clan_id=5,
        player_id=player_id,
        moscow_date=_MOSCOW_TODAY,
        source=DailyHeadSource.BUTTON,
        bonus_cm=bonus_cm,
        assigned_at=_NOW,
    )


def _resolved(
    *,
    was_new: bool = True,
    bonus_cm: int = 15,
    player: Player | None = None,
) -> DailyHeadResolved:
    return DailyHeadResolved(
        assignment=_assignment(bonus_cm=bonus_cm),
        player=player if player is not None else _player(),
        was_new=was_new,
    )


def _stub_clans(*, clan: Clan | None) -> MagicMock:
    repo = MagicMock(spec=IClanRepository)
    repo.get_by_chat_id = AsyncMock(return_value=clan)
    return repo


def _stub_use_case(
    *,
    result: DailyHeadResolved | None = None,
    error: Exception | None = None,
) -> MagicMock:
    uc = MagicMock(spec=RequestDailyHead)
    if error is not None:
        uc.execute = AsyncMock(side_effect=error)
    else:
        uc.execute = AsyncMock(return_value=result)
    return uc


def _quote_provider(
    *,
    ru: tuple[ClanQuoteTemplate, ...] = (),
    en: tuple[ClanQuoteTemplate, ...] = (),
) -> FakeClanQuoteTemplateProvider:
    catalog: dict[str, tuple[ClanQuoteTemplate, ...]] = {}
    if ru:
        catalog["ru"] = ru
    if en:
        catalog["en"] = en
    return FakeClanQuoteTemplateProvider(catalog=catalog)


def _quote(
    *,
    quote_id: str = "clan_quote.ru.0001",
    text: str = "По понятиям, {user}!",
) -> ClanQuoteTemplate:
    return ClanQuoteTemplate(id=quote_id, text=text, tags=("statham",))


@pytest.mark.asyncio
class TestHandleClanHead:
    async def test_no_identity_is_silent_no_op(self) -> None:
        msg = _msg()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            None,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_not_called()
        clans.get_by_chat_id.assert_not_called()
        uc.execute.assert_not_called()

    async def test_private_chat_replies_with_needs_group_chat(self) -> None:
        msg = _msg(chat_type="private", chat_id=42)
        identity = _identity(chat_kind="private", chat_id=42)
        clans = _stub_clans(clan=None)
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-head-needs-group-chat")
        clans.get_by_chat_id.assert_not_called()
        uc.execute.assert_not_called()

    async def test_channel_chat_replies_with_needs_group_chat(self) -> None:
        # Telegram chat_kind for channels is "channel" — handler treats it as not-group.
        msg = _msg(chat_type="channel", chat_id=-200)
        identity = _identity(chat_kind="channel", chat_id=-200)
        clans = _stub_clans(clan=None)
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("en"),
        )

        msg.answer.assert_awaited_once_with("en:clan-head-needs-group-chat")
        uc.execute.assert_not_called()

    async def test_group_chat_without_clan_replies_not_registered(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=None)
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-head-not-registered")
        clans.get_by_chat_id.assert_awaited_once_with(-100100)
        uc.execute.assert_not_called()

    async def test_group_chat_clan_without_id_replies_not_registered(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(clan_id=None))
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-head-not-registered")
        uc.execute.assert_not_called()

    async def test_frozen_clan_replies_with_frozen_clan(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(error=ClanFrozenError(chat_id=-100100))
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-head-frozen-clan")
        uc.execute.assert_awaited_once()

    async def test_insufficient_activity_replies_with_active_and_required(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(
            error=DailyHeadInsufficientActivityError(clan_id=5, active_count=2, required=5)
        )
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with(
            "ru:clan-head-not-enough-active[active_count=2,required=5]"
        )

    async def test_success_renders_localized_card_with_quote_and_username(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        player = _player(username="alice")
        uc = _stub_use_case(result=_resolved(player=player, bonus_cm=15))
        # FakeRandom.choice returns the first item by default.
        provider = _quote_provider(ru=(_quote(text="По понятиям, {user}!"),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # head_display_name = "@alice" (no first_name passed in by handler);
        # quote_text has {user} replaced with the same display name.
        assert sent.startswith("ru:clan-head-success[")
        assert "head_display_name=@alice" in sent
        assert "bonus_cm=15" in sent
        assert "new_length_cm=120" in sent
        assert "quote_text=По понятиям, @alice!" in sent

    async def test_already_assigned_renders_localized_card(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        player = _player(username="bob")
        uc = _stub_use_case(result=_resolved(was_new=False, player=player, bonus_cm=10))
        provider = _quote_provider(
            en=(_quote(quote_id="clan_quote.en.0001", text="Statham approves, {user}."),)
        )
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:clan-head-already-assigned[")
        assert "head_display_name=@bob" in sent
        assert "bonus_cm=10" in sent
        assert "quote_text=Statham approves, @bob." in sent
        # `new_length_cm` is NOT a placeholder of `already-assigned`.
        assert "new_length_cm" not in sent

    async def test_empty_quote_catalog_falls_back_to_default(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider()  # empty catalog
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        sent = msg.answer.await_args.args[0]
        # Fallback quote `_FALLBACK_QUOTE` = "👑" is rendered as `quote_text=👑`.
        assert "quote_text=👑" in sent

    async def test_player_without_username_uses_glava_fallback(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        player = _player(username=None)
        uc = _stub_use_case(result=_resolved(player=player))
        provider = _quote_provider(ru=(_quote(text="Уважение, {user}."),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        sent = msg.answer.await_args.args[0]
        assert "head_display_name=глава" in sent
        assert "quote_text=Уважение, глава." in sent

    async def test_locale_none_falls_back_to_default(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            None,
        )

        sent = msg.answer.await_args.args[0]
        # DEFAULT_LOCALE = "en" (per i18n module).
        assert sent.startswith("en:clan-head-")

    async def test_group_chat_kind_is_supported(self) -> None:
        # `chat_kind` may be either "group" or "supergroup".
        msg = _msg(chat_type="group", chat_id=-200)
        identity = _identity(chat_kind="group", chat_id=-200)
        clans = _stub_clans(clan=_clan(chat_id=-200))
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        clans.get_by_chat_id.assert_awaited_once_with(-200)
        uc.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()

    async def test_use_case_invoked_with_chat_id_and_actor_tg_id(self) -> None:
        msg = _msg(chat_id=-555)
        identity = _identity(chat_id=-555)
        clans = _stub_clans(clan=_clan(chat_id=-555))
        uc = _stub_use_case(result=_resolved())
        provider = _quote_provider(ru=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once()
        called_input = uc.execute.await_args.args[0]
        assert called_input.chat_id == -555
        assert called_input.actor_tg_id == 100

    async def test_quote_provider_called_with_locale_code(self) -> None:
        msg = _msg()
        identity = _identity()
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case(result=_resolved())
        provider = MagicMock(spec=IClanQuoteTemplateProvider)
        provider.get_templates = MagicMock(return_value=(_quote(),))
        rng = FakeRandom()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_head(
            cast(Message, msg),
            identity,
            cast(RequestDailyHead, uc),
            cast(IClanRepository, clans),
            cast(IClanQuoteTemplateProvider, provider),
            cast(IRandom, rng),
            bundle,
            Locale("en"),
        )

        provider.get_templates.assert_called_once_with(locale="en")
