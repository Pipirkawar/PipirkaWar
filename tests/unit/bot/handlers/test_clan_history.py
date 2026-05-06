"""\u042e\u043d\u0438\u0442-\u0442\u0435\u0441\u0442\u044b `/clan_history`-handler-\u0430 (\u0421\u043f\u0440\u0438\u043d\u0442 2.2.G / \u041f\u0414 2.2.5).

\u041f\u043e\u043a\u0440\u044b\u0432\u0430\u0435\u043c \u0432\u0441\u0435 \u0432\u0435\u0442\u043a\u0438 handler-\u0430:
* \u0432 \u041b\u0421 / \u043d\u0435 \u0432 \u0433\u0440\u0443\u043f\u043f\u043e\u0432\u043e\u043c \u0447\u0430\u0442\u0435 \u2192 `clan-history-needs-group-chat`;
* \u0432 \u0433\u0440\u0443\u043f\u043f\u043e\u0432\u043e\u043c \u0447\u0430\u0442\u0435, \u043d\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d\u043d\u043e\u043c \u043a \u043a\u043b\u0430\u043d\u0443 \u2192 `clan-history-not-registered`;
* \u0432 \u0433\u0440\u0443\u043f\u043f\u043e\u0432\u043e\u043c \u0447\u0430\u0442\u0435 \u043a\u043b\u0430\u043d\u0430 \u0431\u0435\u0437 \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u2192 `clan-history-empty`;
* \u0432 \u0433\u0440\u0443\u043f\u043f\u043e\u0432\u043e\u043c \u0447\u0430\u0442\u0435 \u043a\u043b\u0430\u043d\u0430 \u0441 \u0438\u0441\u0442\u043e\u0440\u0438\u0435\u0439 \u2192 `clan-history-header` + entries;
* `tg_identity is None` \u2192 \u0442\u0438\u0445\u0438\u0439 no-op (\u0431\u0435\u0437 \u043e\u0442\u0432\u0435\u0442\u0430);
* fallback \u043b\u043e\u043a\u0430\u043b\u0438 \u043f\u0440\u0438 `locale=None` \u2192 `DEFAULT_LOCALE`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.pvp import GetClanAttackHistory
from pipirik_wars.bot.handlers.clan_history import handle_clan_history
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
    IClanRepository,
)
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
    MassDuelState,
)
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def _msg(*, chat_type: str = "supergroup", chat_id: int = -100100) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(
        id=100, is_bot=False, first_name="\u0410\u043b\u0438\u0441\u0430", username="alice"
    )
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
    title: str = "\u041b\u0435\u0441\u043d\u044b\u0435",
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


def _entry_victory(
    *, opponent_title: str = "\u041c\u043e\u0440\u0441\u043a\u0438\u0435"
) -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=1,
        our_clan_id=5,
        opponent_clan_id=20,
        opponent_clan_title=ClanTitle(value=opponent_title),
        state=MassDuelState.COMPLETED,
        outcome=ClanMassDuelOutcomeForUs.VICTORY,
        our_total_dealt=30,
        our_total_received=10,
        our_delta_cm=20,
        opponent_delta_cm=-20,
        our_participants_count=2,
        opponent_participants_count=2,
        created_at=_NOW,
        completed_at=_NOW,
    )


def _stub_clans(*, clan: Clan | None) -> MagicMock:
    repo = MagicMock(spec=IClanRepository)
    repo.get_by_chat_id = AsyncMock(return_value=clan)
    return repo


def _stub_use_case(entries: list[ClanMassDuelHistoryEntry]) -> MagicMock:
    uc = MagicMock(spec=GetClanAttackHistory)
    uc.execute = AsyncMock(return_value=tuple(entries))
    return uc


@pytest.mark.asyncio
class TestHandleClanHistory:
    async def test_private_chat_replies_with_needs_group_chat(self) -> None:
        msg = _msg(chat_type="private", chat_id=42)
        identity = _identity(chat_kind="private", chat_id=42)
        clans = _stub_clans(clan=None)
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-history-needs-group-chat")
        uc.execute.assert_not_called()
        clans.get_by_chat_id.assert_not_called()

    async def test_group_chat_without_registered_clan_replies_not_registered(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=None)
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("en"),
        )

        msg.answer.assert_awaited_once_with("en:clan-history-not-registered")
        uc.execute.assert_not_called()
        clans.get_by_chat_id.assert_awaited_once_with(-100100)

    async def test_group_chat_clan_without_id_replies_not_registered(self) -> None:
        # \u0422\u0435\u043e\u0440\u0435\u0442\u0438\u0447\u0435\u0441\u043a\u0438 `Clan.id is None` \u043d\u0435 \u0431\u044b\u0432\u0430\u0435\u0442 \u043f\u043e\u0441\u043b\u0435 add(),
        # \u043d\u043e handler \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0443\u0441\u0442\u043e\u0439\u0447\u0438\u0432 \u043a \u043b\u044e\u0431\u043e\u043c\u0443 None.
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(clan_id=None))
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:clan-history-not-registered")
        uc.execute.assert_not_called()

    async def test_empty_history_replies_with_empty_message(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(title="\u041b\u044c\u0432\u044b"))
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with(clan_id=5)
        msg.answer.assert_awaited_once_with(
            "ru:clan-history-empty[clan_title=\u041b\u044c\u0432\u044b]"
        )

    async def test_non_empty_history_renders_header_and_entries(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(title="\u041b\u044c\u0432\u044b"))
        uc = _stub_use_case([_entry_victory()])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        uc.execute.assert_awaited_once_with(clan_id=5)
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:clan-history-header[clan_title=\u041b\u044c\u0432\u044b]")
        assert "ru:clan-history-entry-victory[" in sent

    async def test_group_chat_supports_both_group_and_supergroup(self) -> None:
        # `chat_kind` \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043a\u0430\u043a "group", \u0442\u0430\u043a \u0438 "supergroup".
        msg = _msg(chat_type="group", chat_id=-200)
        identity = _identity(chat_kind="group", chat_id=-200)
        clans = _stub_clans(clan=_clan(chat_id=-200))
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        clans.get_by_chat_id.assert_awaited_once_with(-200)
        uc.execute.assert_awaited_once_with(clan_id=5)

    async def test_no_locale_falls_back_to_default(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(title="Lions"))
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:clan-history-empty[clan_title=Lions]")

    async def test_no_identity_is_silent_no_op(self) -> None:
        msg = _msg(chat_type="supergroup")
        clans = _stub_clans(clan=_clan())
        uc = _stub_use_case([])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            None,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("ru"),
        )

        msg.answer.assert_not_called()
        clans.get_by_chat_id.assert_not_called()
        uc.execute.assert_not_called()

    async def test_locale_propagates_to_bundle(self) -> None:
        msg = _msg(chat_type="supergroup")
        identity = _identity(chat_kind="supergroup")
        clans = _stub_clans(clan=_clan(title="Lions"))
        uc = _stub_use_case([_entry_victory(opponent_title="Sharks")])
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_clan_history(
            cast(Message, msg),
            identity,
            cast(GetClanAttackHistory, uc),
            cast(IClanRepository, clans),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:clan-history-header[clan_title=Lions]")
        assert "en:clan-history-entry-victory[" in sent
