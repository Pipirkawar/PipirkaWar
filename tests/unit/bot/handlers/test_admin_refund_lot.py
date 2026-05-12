"""Unit-тесты handler-а `/refund_lot` (Спринт 4.1-E, E.13).

Покрывает фазу 1 — `handle_refund_lot`:
- non-private chat / отсутствие identity → REPLY_NON_PRIVATE_RU.
- пустые args / только lot_id / отсутствует reason → usage.
- неверный lot_id (нечисло / 0 / отрицательное) → bad_lot_id.
- AuthorizationError / TotpNotConfiguredError из RequestAdminConfirm →
  соответствующие отказы.
- успешный путь → confirm_issued с token и ttl_seconds.

Фаза 2 (dispatch_refund_lot) живёт в `admin_refund_lot.py` и покрывается
отдельно в E.13.c — здесь её ещё нет.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    RequestAdminConfirm,
    RequestAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_refund_lot import (
    COMMAND_KIND_REFUND_LOT,
    REPLY_NON_PRIVATE_RU,
    handle_refund_lot,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError

_RU = Locale("ru")


class _StubBundle(IMessageBundle):
    def format(self, key: MessageKey, *, locale: Locale, **kwargs: object) -> str:
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
    return CommandObject(prefix="/", command="refund_lot", mention=None, args=args)


def _stub_request_confirm(
    *,
    output: RequestAdminConfirmOutput | None = None,
) -> RequestAdminConfirm:
    fake = MagicMock(spec=RequestAdminConfirm)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(RequestAdminConfirm, fake)


def _confirm_token() -> RequestAdminConfirmOutput:
    return RequestAdminConfirmOutput(token="TOK-REFUND", ttl_seconds=60)


@pytest.mark.asyncio
class TestHandleRefundLot:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        rc = _stub_request_confirm()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 stuck reservation"),
            tg_identity=_identity(chat_kind="group"),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 stuck reservation"),
            tg_identity=None,
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-usage" in msg.answer.await_args.args[0]

    async def test_only_lot_id_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-usage" in msg.answer.await_args.args[0]

    async def test_bad_lot_id_non_int(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("abc stuck"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-bad-lot-id" in text
        assert "value=abc" in text

    async def test_bad_lot_id_zero(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("0 reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-bad-lot-id" in msg.answer.await_args.args[0]

    async def test_bad_lot_id_negative(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("-5 reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-bad-lot-id" in msg.answer.await_args.args[0]

    async def test_trailing_whitespace_after_lot_id_replies_usage(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        # `command.args = "42    "` → `.strip()` вырежет trailing
        # whitespace, получим `raw = "42"`, parts = ["42"], len < 2
        # → usage-отказ (такие кейсы эквивалентны только первому аргументу).
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42    "),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-usage" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 stuck reservation"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-not-authorized" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=TotpNotConfiguredError("no totp"),
        )
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 stuck reservation"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-refund-lot-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 stuck reservation"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-confirm-issued" in text
        assert "token=TOK-REFUND" in text
        assert "ttl_seconds=60" in text

        # Контракт payload-а зафиксирован для dispatch_refund_lot (E.13.c).
        rc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_REFUND_LOT
        assert call_input.target_kind == "prize_lot"
        assert call_input.target_id == "42"
        assert call_input.actor_tg_id == 42
        assert call_input.tg_chat_id == 42
        assert dict(call_input.payload) == {
            "lot_id": 42,
            "reason": "stuck reservation",
        }

    async def test_default_locale_when_locale_is_none(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_refund_lot(
            message=cast(Message, msg),
            command=_command("42 reason"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=None,
        )
        # DEFAULT_LOCALE = "en" (см. application.i18n.DEFAULT_LOCALE).
        assert "|en|" in msg.answer.await_args.args[0]
