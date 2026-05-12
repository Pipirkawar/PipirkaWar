"""Unit-тесты handler-ов `/freeze_payouts` и `/unfreeze_payouts` (Спринт 4.1-E, E.14).

Покрывает фазу 1 (`handle_freeze_payouts` / `handle_unfreeze_payouts`):

`/freeze_payouts <reason>`:
- non-private chat / отсутствие identity → REPLY_NON_PRIVATE_RU.
- пустые args / только whitespace → no_reason.
- AuthorizationError / TotpNotConfiguredError из RequestAdminConfirm →
  соответствующие отказы (`not_authorized` / `totp_not_configured`).
- успешный путь → confirm_issued с token и ttl_seconds + проверка контракта
  `RequestAdminConfirmInput` (command_kind, target_kind, target_id, payload).

`/unfreeze_payouts`:
- non-private chat / отсутствие identity → REPLY_NON_PRIVATE_RU.
- AuthorizationError / TotpNotConfiguredError из RequestAdminConfirm →
  соответствующие отказы.
- успешный путь → confirm_issued с token и ttl_seconds + проверка контракта
  `RequestAdminConfirmInput` (пустой payload).

Фаза 2 (dispatch_*) добавится в E.14.c — её тесты живут отдельно.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    BanPlayer,
    GrantLength,
    GrantThickness,
    IBroadcastTaskSpawner,
    RequestAdminConfirm,
    RequestAdminConfirmOutput,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import (
    FreezePayouts,
    FreezePayoutsOutput,
    RefundLot,
    UnfreezePayouts,
    UnfreezePayoutsOutput,
)
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.handlers.admin_freeze_payouts import (
    COMMAND_KIND_FREEZE_PAYOUTS,
    COMMAND_KIND_UNFREEZE_PAYOUTS,
    REPLY_NON_PRIVATE_RU,
    dispatch_freeze_payouts,
    dispatch_unfreeze_payouts,
    handle_freeze_payouts,
    handle_unfreeze_payouts,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.shared.ports import IClock

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
    return CommandObject(prefix="/", command="freeze_payouts", mention=None, args=args)


def _stub_request_confirm(
    *,
    output: RequestAdminConfirmOutput | None = None,
) -> RequestAdminConfirm:
    fake = MagicMock(spec=RequestAdminConfirm)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(RequestAdminConfirm, fake)


def _confirm_token() -> RequestAdminConfirmOutput:
    return RequestAdminConfirmOutput(token="TOK-FREEZE", ttl_seconds=60)


@pytest.mark.asyncio
class TestHandleFreezePayouts:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        rc = _stub_request_confirm()
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("payouts exploit suspected"),
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
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("payouts exploit suspected"),
            tg_identity=None,
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args_replies_no_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-payouts-no-reason" in msg.answer.await_args.args[0]
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_whitespace_only_args_replies_no_reason(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("    "),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-payouts-no-reason" in msg.answer.await_args.args[0]
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_none_args_replies_no_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command(None),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-payouts-no-reason" in msg.answer.await_args.args[0]
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("exploit"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-payouts-not-authorized" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=TotpNotConfiguredError("no totp"),
        )
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("exploit"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-payouts-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("payouts exploit suspected"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-payouts-confirm-issued" in text
        assert "token=TOK-FREEZE" in text
        assert "ttl_seconds=60" in text

        # Контракт payload-а зафиксирован для dispatch_freeze_payouts (E.14.c).
        rc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_FREEZE_PAYOUTS
        assert call_input.target_kind == "payout_freeze"
        assert call_input.target_id == "all"
        assert call_input.actor_tg_id == 42
        assert call_input.tg_chat_id == 42
        assert dict(call_input.payload) == {"reason": "payouts exploit suspected"}

    async def test_reason_with_surrounding_whitespace_is_trimmed(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("   exploit detected   "),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        rc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert dict(call_input.payload) == {"reason": "exploit detected"}

    async def test_default_locale_when_locale_is_none(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_freeze_payouts(
            message=cast(Message, msg),
            command=_command("reason"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=None,
        )
        # DEFAULT_LOCALE = "en" (см. application.i18n.DEFAULT_LOCALE).
        assert "|en|" in msg.answer.await_args.args[0]


# ── /freeze_payouts фаза 2 + /unfreeze_payouts фаза 2 (диспетчеры) ────────────────


def _fixed_clock() -> IClock:
    fake = MagicMock(spec=IClock)
    fake.now = MagicMock(return_value=datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC))
    return cast(IClock, fake)


def _stub_freeze_payouts(
    *,
    output: FreezePayoutsOutput | None = None,
    raises: Exception | None = None,
) -> FreezePayouts:
    fake = MagicMock(spec=FreezePayouts)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(FreezePayouts, fake)


def _stub_unfreeze_payouts(
    *,
    output: UnfreezePayoutsOutput | None = None,
    raises: Exception | None = None,
) -> UnfreezePayouts:
    fake = MagicMock(spec=UnfreezePayouts)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(UnfreezePayouts, fake)


def _deps(
    *,
    freeze_payouts: FreezePayouts | None = None,
    unfreeze_payouts: UnfreezePayouts | None = None,
) -> ConfirmDispatchDeps:
    """Фабрика `ConfirmDispatchDeps` для dispatch_(un)freeze_payouts-тестов.

    Диспетчеры используют только `deps.freeze_payouts` / `deps.unfreeze_payouts`,
    но `ConfirmDispatchDeps`-frozen-dataclass обязывает предоставить все поля
    — остальные spec-моки (не вызываются в этих тестах).
    """
    return ConfirmDispatchDeps(
        grant_length=cast(GrantLength, MagicMock(spec=GrantLength)),
        grant_thickness=cast(GrantThickness, MagicMock(spec=GrantThickness)),
        set_balance_value=cast(SetBalanceValue, MagicMock(spec=SetBalanceValue)),
        ban_player=cast(BanPlayer, MagicMock(spec=BanPlayer)),
        run_broadcast_announcement=cast(
            RunBroadcastAnnouncement,
            MagicMock(spec=RunBroadcastAnnouncement),
        ),
        broadcast_task_spawner=cast(
            IBroadcastTaskSpawner,
            MagicMock(spec=IBroadcastTaskSpawner),
        ),
        clock=_fixed_clock(),
        refund_lot=cast(RefundLot, MagicMock(spec=RefundLot)),
        freeze_payouts=freeze_payouts or _stub_freeze_payouts(),
        unfreeze_payouts=unfreeze_payouts or _stub_unfreeze_payouts(),
    )


def _verify_freeze_output(
    *,
    reason: str = "exploit",
    payload_override: dict[str, object] | None = None,
) -> VerifyAdminConfirmOutput:
    payload: dict[str, object] = (
        payload_override if payload_override is not None else {"reason": reason}
    )
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_FREEZE_PAYOUTS,
        target_kind="payout_freeze",
        target_id="all",
        payload=MappingProxyType(payload),
    )


def _verify_unfreeze_output() -> VerifyAdminConfirmOutput:
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_UNFREEZE_PAYOUTS,
        target_kind="payout_freeze",
        target_id="all",
        payload=MappingProxyType({}),
    )


@pytest.mark.asyncio
class TestDispatchFreezePayouts:
    async def test_registered_in_dispatcher_map(self) -> None:
        """`COMMAND_KIND_FREEZE_PAYOUTS` зарегистрирован при импорте модуля."""
        assert CONFIRM_DISPATCHERS.get(COMMAND_KIND_FREEZE_PAYOUTS) is dispatch_freeze_payouts

    async def test_payload_invalid_reason_missing(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await dispatch_freeze_payouts(
            result=_verify_freeze_output(payload_override={}),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_payload_invalid_reason_wrong_type(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        await dispatch_freeze_payouts(
            result=_verify_freeze_output(payload_override={"reason": 42}),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_payouts(raises=AuthorizationError(requirement="x", detail="y"))
        await dispatch_freeze_payouts(
            result=_verify_freeze_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(freeze_payouts=uc),
        )
        assert "admin-freeze-payouts-not-authorized" in msg.answer.await_args.args[0]

    async def test_already_frozen_idempotent(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_payouts(
            output=FreezePayoutsOutput(is_frozen=True, was_already_frozen=True),
        )
        await dispatch_freeze_payouts(
            result=_verify_freeze_output(reason="exploit"),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(freeze_payouts=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-payouts-already-frozen" in text
        assert "reason=exploit" in text

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze_payouts(
            output=FreezePayoutsOutput(is_frozen=True, was_already_frozen=False),
        )
        await dispatch_freeze_payouts(
            result=_verify_freeze_output(reason="jetton-bug"),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(freeze_payouts=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-payouts-success" in text
        assert "reason=jetton-bug" in text

        # Контракт `FreezePayoutsInput`-вызова: reason из payload,
        # actor_tg_id и tg_chat_id — из identity.
        uc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = uc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.actor_tg_id == 42
        assert call_input.reason == "jetton-bug"
        assert call_input.tg_chat_id == 42


@pytest.mark.asyncio
class TestDispatchUnfreezePayouts:
    async def test_registered_in_dispatcher_map(self) -> None:
        """`COMMAND_KIND_UNFREEZE_PAYOUTS` зарегистрирован при импорте модуля."""
        assert CONFIRM_DISPATCHERS.get(COMMAND_KIND_UNFREEZE_PAYOUTS) is dispatch_unfreeze_payouts

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_payouts(
            raises=AuthorizationError(requirement="x", detail="y"),
        )
        await dispatch_unfreeze_payouts(
            result=_verify_unfreeze_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(unfreeze_payouts=uc),
        )
        assert "admin-unfreeze-payouts-not-authorized" in msg.answer.await_args.args[0]

    async def test_already_unfrozen_idempotent(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_payouts(
            output=UnfreezePayoutsOutput(is_frozen=False, was_already_unfrozen=True),
        )
        await dispatch_unfreeze_payouts(
            result=_verify_unfreeze_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(unfreeze_payouts=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-unfreeze-payouts-already-unfrozen" in text

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze_payouts(
            output=UnfreezePayoutsOutput(is_frozen=False, was_already_unfrozen=False),
        )
        await dispatch_unfreeze_payouts(
            result=_verify_unfreeze_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(unfreeze_payouts=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-unfreeze-payouts-success" in text

        # Контракт `UnfreezePayoutsInput`-вызова: reason=None (use-case сам
        # ставит дефолт), actor_tg_id и tg_chat_id — из identity.
        uc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = uc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.actor_tg_id == 42
        assert call_input.reason is None
        assert call_input.tg_chat_id == 42


@pytest.mark.asyncio
class TestHandleUnfreezePayouts:
    async def test_non_private_chat_replies_only_dm(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock(chat_type="group")
        rc = _stub_request_confirm()
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
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
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
            tg_identity=None,
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        rc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-unfreeze-payouts-not-authorized" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=TotpNotConfiguredError("no totp"),
        )
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-unfreeze-payouts-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-unfreeze-payouts-confirm-issued" in text
        assert "token=TOK-FREEZE" in text
        assert "ttl_seconds=60" in text

        # Контракт payload-а зафиксирован для dispatch_unfreeze_payouts (E.14.c):
        # пустой, так как unfreeze не имеет параметров.
        rc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_UNFREEZE_PAYOUTS
        assert call_input.target_kind == "payout_freeze"
        assert call_input.target_id == "all"
        assert call_input.actor_tg_id == 42
        assert call_input.tg_chat_id == 42
        assert dict(call_input.payload) == {}

    async def test_default_locale_when_locale_is_none(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_unfreeze_payouts(
            message=cast(Message, msg),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=None,
        )
        # DEFAULT_LOCALE = "en" (см. application.i18n.DEFAULT_LOCALE).
        assert "|en|" in msg.answer.await_args.args[0]
