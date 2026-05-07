"""Unit-тесты handler-ов `/freeze_clan` / `/unfreeze_clan` (Спринт 2.5-D.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    FreezeClanAdmin,
    FreezeClanAdminOutput,
    UnfreezeClanAdmin,
    UnfreezeClanAdminOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_clan import (
    REPLY_NON_PRIVATE_RU,
    handle_freeze_clan,
    handle_unfreeze_clan,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
)
from pipirik_wars.domain.clan.value_objects import ClanTitle

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


def _command(name: str, args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command=name, mention=None, args=args)


def _seed_clan(*, clan_id: int, status: ClanStatus = ClanStatus.ACTIVE) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=-100500,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value="C"),
        status=status,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def _stub_freeze_uc(*, output: FreezeClanAdminOutput | None = None) -> FreezeClanAdmin:
    fake = MagicMock(spec=FreezeClanAdmin)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(FreezeClanAdmin, fake)


def _stub_unfreeze_uc(
    *,
    output: UnfreezeClanAdminOutput | None = None,
) -> UnfreezeClanAdmin:
    fake = MagicMock(spec=UnfreezeClanAdmin)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(UnfreezeClanAdmin, fake)


@pytest.mark.asyncio
class TestHandleFreezeClan:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_freeze_uc()
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", None),
            tg_identity=_identity(chat_kind="group"),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_missing_identity_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_uc()
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", None),
            tg_identity=None,
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_empty_args_shows_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_uc()
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", ""),
            tg_identity=_identity(),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-usage|ru|")

    async def test_bad_id_friendly_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_uc()
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", "abc reason text"),
            tg_identity=_identity(),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-bad-id|ru|")

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        fake = MagicMock(spec=FreezeClanAdmin)
        fake.execute = AsyncMock(
            side_effect=AuthorizationError(requirement="admin_active", detail="x"),
        )
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", "1"),
            tg_identity=_identity(),
            freeze_clan_admin=cast(FreezeClanAdmin, fake),
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-not-authorized|ru|")

    async def test_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_uc(
            output=FreezeClanAdminOutput(query=999, outcome="not_found", clan=None),
        )
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", "999"),
            tg_identity=_identity(),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-not-found|ru|")
        assert "query=999" in called

    async def test_already_frozen(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        clan = _seed_clan(clan_id=7, status=ClanStatus.FROZEN)
        uc = _stub_freeze_uc(
            output=FreezeClanAdminOutput(query=7, outcome="already_frozen", clan=clan),
        )
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", "7"),
            tg_identity=_identity(),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-already|ru|")
        assert "clan_id=7" in called

    async def test_freeze_ok_with_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        clan = _seed_clan(clan_id=7, status=ClanStatus.FROZEN)
        uc = _stub_freeze_uc(
            output=FreezeClanAdminOutput(query=7, outcome="frozen", clan=clan),
        )
        await handle_freeze_clan(
            message=cast(Message, msg),
            command=_command("freeze_clan", "7 abuse"),
            tg_identity=_identity(),
            freeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-freeze-clan-ok|ru|")
        assert "clan_id=7" in called


@pytest.mark.asyncio
class TestHandleUnfreezeClan:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_unfreeze_uc()
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", None),
            tg_identity=_identity(chat_kind="group"),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_missing_identity_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_uc()
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", None),
            tg_identity=None,
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_empty_args_shows_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_uc()
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", ""),
            tg_identity=_identity(),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-usage|ru|")

    async def test_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_uc()
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", "abc"),
            tg_identity=_identity(),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-bad-id|ru|")

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        fake = MagicMock(spec=UnfreezeClanAdmin)
        fake.execute = AsyncMock(
            side_effect=AuthorizationError(requirement="admin_active", detail="x"),
        )
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", "1"),
            tg_identity=_identity(),
            unfreeze_clan_admin=cast(UnfreezeClanAdmin, fake),
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-not-authorized|ru|")

    async def test_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_uc(
            output=UnfreezeClanAdminOutput(
                query=999,
                outcome="not_found",
                clan=None,
            ),
        )
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", "999"),
            tg_identity=_identity(),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-not-found|ru|")

    async def test_already_active(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        clan = _seed_clan(clan_id=7, status=ClanStatus.ACTIVE)
        uc = _stub_unfreeze_uc(
            output=UnfreezeClanAdminOutput(
                query=7,
                outcome="already_active",
                clan=clan,
            ),
        )
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", "7"),
            tg_identity=_identity(),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-already|ru|")
        assert "clan_id=7" in called

    async def test_unfreeze_ok(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        clan = _seed_clan(clan_id=7, status=ClanStatus.ACTIVE)
        uc = _stub_unfreeze_uc(
            output=UnfreezeClanAdminOutput(
                query=7,
                outcome="unfrozen",
                clan=clan,
            ),
        )
        await handle_unfreeze_clan(
            message=cast(Message, msg),
            command=_command("unfreeze_clan", "7"),
            tg_identity=_identity(),
            unfreeze_clan_admin=uc,
            bundle=bundle,
            locale=_RU,
        )
        called = msg.answer.await_args.args[0]
        assert called.startswith("admin-unfreeze-clan-ok|ru|")
        assert "clan_id=7" in called
