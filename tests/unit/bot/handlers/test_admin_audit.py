"""Unit-тесты handler-а `/audit` (Спринт 2.5-D.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    AdminAuditActionUnknownError,
    GetAdminAuditTrail,
    GetAdminAuditTrailOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_audit import (
    REPLY_NON_PRIVATE_RU,
    handle_audit,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditRecord,
    AdminAuditSource,
)

_RU = Locale("ru")


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
    return CommandObject(prefix="/", command="audit", mention=None, args=args)


def _stub_uc(*, output: GetAdminAuditTrailOutput | None = None) -> GetAdminAuditTrail:
    fake = MagicMock(spec=GetAdminAuditTrail)
    if output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(GetAdminAuditTrail, fake)


def _record(
    *,
    rec_id: int = 1,
    action: AdminAuditAction = AdminAuditAction.ADMIN_PLAYER_FROZEN,
) -> AdminAuditRecord:
    return AdminAuditRecord(
        id=rec_id,
        actor_admin_id=1,
        actor_tg_id=10,
        action=action,
        target_kind="player",
        target_id="42",
        before=None,
        after=None,
        reason="r",
        idempotency_key=None,
        source=AdminAuditSource.BOT,
        tg_chat_id=None,
        ip=None,
        occurred_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
class TestHandleAudit:
    async def test_non_private_chat_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_uc()
        await handle_audit(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=_identity(chat_kind="group"),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_audit(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=None,
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error_replies_not_authorized(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_audit(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-not-authorized" in text

    async def test_unknown_action_replies_message(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AdminAuditActionUnknownError(value="bogus"),
        )
        await handle_audit(
            message=cast(Message, msg),
            command=_command("- bogus"),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-unknown-action" in text
        assert "bogus" in text

    async def test_bad_tg_id_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_audit(
            message=cast(Message, msg),
            command=_command("notanint"),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-bad-tg-id" in text
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_bad_limit_replies(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_audit(
            message=cast(Message, msg),
            command=_command("- - notanint"),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-bad-limit" in text
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_target_not_found_replies(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(
            output=GetAdminAuditTrailOutput(
                target_admin_tg_id=999,
                target_admin_resolved=False,
                action=None,
                limit=20,
                records=(),
            ),
        )
        await handle_audit(
            message=cast(Message, msg),
            command=_command("999"),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-target-not-found" in text

    async def test_empty_replies_empty(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(
            output=GetAdminAuditTrailOutput(
                target_admin_tg_id=None,
                target_admin_resolved=True,
                action=None,
                limit=20,
                records=(),
            ),
        )
        await handle_audit(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-empty" in text

    async def test_renders_records_with_header_and_rows(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_uc(
            output=GetAdminAuditTrailOutput(
                target_admin_tg_id=10,
                target_admin_resolved=True,
                action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
                limit=20,
                records=(_record(rec_id=1), _record(rec_id=2)),
            ),
        )
        await handle_audit(
            message=cast(Message, msg),
            command=_command("10 admin_player_frozen"),
            tg_identity=_identity(),
            get_admin_audit_trail=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-audit-header-target" in text
        assert "admin-audit-filter-action-suffix" in text
        # Две строки + заголовок (+ suffix), потому что render склеивает через \n.
        assert text.count("admin-audit-row") == 2
