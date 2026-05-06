"""Unit-тесты handler-а `/clan` (Спринт 2.5-D.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    ClanCard,
    ClanMemberCardInfo,
    GetClanCard,
    GetClanCardOutput,
    PlayerSummary,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_clan import (
    REPLY_NON_PRIVATE_RU,
    handle_clan,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.clan import ClanMemberRole, ClanStatus
from pipirik_wars.domain.player import PlayerStatus

_RU = Locale("ru")
_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


class _StubBundle(IMessageBundle):
    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **kwargs: object,
    ) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


def _msg_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="clan", mention=None, args=args)


def _stub_uc(*, output: GetClanCardOutput | None = None) -> GetClanCard:
    fake = MagicMock(spec=GetClanCard)
    if output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(GetClanCard, fake)


def _summary(tg_id: int = 100) -> PlayerSummary:
    return PlayerSummary(
        tg_id=tg_id,
        username="ivan",
        name="Ivan",
        title=None,
        length_cm=10,
        thickness_level=1,
        status=PlayerStatus.ACTIVE,
        anticheat_ban_until=None,
    )


def _card(*, with_leader: bool = True) -> ClanCard:
    leader: ClanMemberCardInfo | None = None
    members: tuple[ClanMemberCardInfo, ...] = ()
    if with_leader:
        leader = ClanMemberCardInfo(
            summary=_summary(tg_id=100),
            role=ClanMemberRole.LEADER,
            joined_at=_FIXED_NOW,
        )
        members = (leader,)
    return ClanCard(
        clan_id=1,
        chat_id=-100500,
        chat_kind="group",
        title="The Pipiriks",
        status=ClanStatus.ACTIVE,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        member_count=len(members),
        active_member_count=len(members),
        total_length_cm=10 if members else 0,
        leader=leader,
        members=members,
    )


@pytest.mark.asyncio
class TestHandleClan:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_uc()
        await handle_clan(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=_identity(chat_kind="group"),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_clan(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=None,
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args_shows_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_clan(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-clan-usage|ru|")
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_bad_id_shows_friendly_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_clan(
            message=cast(Message, msg),
            command=_command("not-a-number"),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-clan-bad-id|ru|")
        assert "value=not-a-number" in called
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error_shows_not_authorized(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        fake = MagicMock(spec=GetClanCard)
        fake.execute = AsyncMock(
            side_effect=AuthorizationError(requirement="admin_active", detail="x"),
        )
        await handle_clan(
            message=cast(Message, msg),
            command=_command("1"),
            tg_identity=_identity(),
            get_clan_card=cast(GetClanCard, fake),
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-clan-not-authorized|ru|")

    async def test_not_found_renders_friendly(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(output=GetClanCardOutput(query=999, card=None))
        await handle_clan(
            message=cast(Message, msg),
            command=_command("999"),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-clan-not-found|ru|")
        assert "query=999" in called

    async def test_render_card(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        card = _card(with_leader=True)
        uc = _stub_uc(output=GetClanCardOutput(query=1, card=card))
        await handle_clan(
            message=cast(Message, msg),
            command=_command("1"),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert "admin-clan-card-summary|ru|" in called
        assert "admin-clan-card-leader|ru|" in called
        assert "admin-clan-card-member-row|ru|" in called

    async def test_render_card_no_leader(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        card = _card(with_leader=False)
        uc = _stub_uc(output=GetClanCardOutput(query=1, card=card))
        await handle_clan(
            message=cast(Message, msg),
            command=_command("1"),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert "admin-clan-card-summary|ru|" in called
        assert "admin-clan-card-no-leader|ru|" in called
        assert "admin-clan-card-no-members|ru|" in called

    async def test_default_locale_when_not_provided(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_uc(output=GetClanCardOutput(query=1, card=None))
        await handle_clan(
            message=cast(Message, msg),
            command=_command("1"),
            tg_identity=_identity(),
            get_clan_card=uc,
            bundle=bundle,
            locale=None,
        )
        called = msg.answer.await_args.args[0]
        # DEFAULT_LOCALE используется (ru).
        assert "|ru|" in called or "|en|" in called
