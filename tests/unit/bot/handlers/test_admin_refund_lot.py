"""Unit-тесты handler-а `/refund_lot` (Спринт 4.1-E, E.13).

Покрывает:

Фаза 1 — `handle_refund_lot`:
- non-private chat / отсутствие identity → REPLY_NON_PRIVATE_RU.
- пустые args / только lot_id / отсутствует reason → usage / no_reason.
- неверный lot_id (нечисло / 0 / отрицательное) → bad_lot_id.
- AuthorizationError / TotpNotConfiguredError из RequestAdminConfirm →
  соответствующие отказы.
- успешный путь → confirm_issued с token и ttl_seconds + проверка контракта
  `RequestAdminConfirmInput` (command_kind, payload).

Фаза 2 — `dispatch_refund_lot` (вызывается из /confirm):
- payload-инвариант (lot_id/reason missing/wrong type) → invalid-payload.
- AuthorizationError → not_authorized.
- PrizeLotNotFoundError → not_found.
- PrizeLotStatusTransitionError (лот в CLAIMED) → bad_transition.
- was_already_refunded=True → already_refunded.
- success-ветка → success с lot_id/currency/amount_native/pool_after.
- регистрация в CONFIRM_DISPATCHERS (по ключу COMMAND_KIND_REFUND_LOT).
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
from pipirik_wars.application.monetization import RefundLot, RefundLotOutput
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.handlers.admin_refund_lot import (
    COMMAND_KIND_REFUND_LOT,
    REPLY_NON_PRIVATE_RU,
    dispatch_refund_lot,
    handle_refund_lot,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.monetization import (
    PrizeLotNotFoundError,
    PrizeLotStatus,
    PrizeLotStatusTransitionError,
)
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


def _fixed_clock() -> IClock:
    fake = MagicMock(spec=IClock)
    fake.now = MagicMock(return_value=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    return cast(IClock, fake)


def _stub_refund_lot(
    *,
    output: RefundLotOutput | None = None,
    raises: Exception | None = None,
) -> RefundLot:
    fake = MagicMock(spec=RefundLot)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(RefundLot, fake)


def _deps(*, refund_lot: RefundLot | None = None) -> ConfirmDispatchDeps:
    """Фабрика `ConfirmDispatchDeps` для dispatch_refund_lot-тестов.

    `dispatch_refund_lot` использует только `deps.refund_lot`, но
    `ConfirmDispatchDeps`-frozen-dataclass обязывает предоставить все
    поля — остальные spec-моки (не вызываются в этих тестах).
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
        refund_lot=refund_lot or _stub_refund_lot(),
    )


def _verify_output(
    *,
    lot_id: int = 42,
    reason: str = "stuck reservation",
    payload_override: dict[str, object] | None = None,
) -> VerifyAdminConfirmOutput:
    payload: dict[str, object] = (
        payload_override if payload_override is not None else {"lot_id": lot_id, "reason": reason}
    )
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_REFUND_LOT,
        target_kind="prize_lot",
        target_id=str(lot_id),
        payload=MappingProxyType(payload),
    )


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


# ── /refund_lot фаза 2 (dispatch_refund_lot) ────────────────────────────────


def _success_output(*, was_already: bool = False) -> RefundLotOutput:
    return RefundLotOutput(
        lot_id=42,
        was_already_refunded=was_already,
        pool_after_native=15_000_000,
        currency="ton",
        amount_native=5_000_000,
    )


@pytest.mark.asyncio
class TestDispatchRefundLot:
    async def test_registered_in_dispatcher_map(self) -> None:
        """`COMMAND_KIND_REFUND_LOT` зарегистрирован при импорте модуля."""
        assert CONFIRM_DISPATCHERS.get(COMMAND_KIND_REFUND_LOT) is dispatch_refund_lot

    async def test_payload_invalid_lot_id_missing(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await dispatch_refund_lot(
            result=_verify_output(payload_override={"reason": "stuck"}),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_payload_invalid_reason_missing(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await dispatch_refund_lot(
            result=_verify_output(payload_override={"lot_id": 42}),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_payload_invalid_lot_id_wrong_type(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        await dispatch_refund_lot(
            result=_verify_output(
                payload_override={"lot_id": "42", "reason": "stuck"},
            ),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_refund_lot(raises=AuthorizationError(requirement="x", detail="y"))
        await dispatch_refund_lot(
            result=_verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(refund_lot=uc),
        )
        assert "admin-refund-lot-not-authorized" in msg.answer.await_args.args[0]

    async def test_lot_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_refund_lot(raises=PrizeLotNotFoundError(lot_id=42))
        await dispatch_refund_lot(
            result=_verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(refund_lot=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-not-found" in text
        assert "lot_id=42" in text

    async def test_bad_transition_claimed_terminal(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_refund_lot(
            raises=PrizeLotStatusTransitionError(
                lot_id=42,
                from_status=PrizeLotStatus.CLAIMED,
                to_status=PrizeLotStatus.REFUNDED,
            ),
        )
        await dispatch_refund_lot(
            result=_verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(refund_lot=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-bad-transition" in text
        assert "lot_id=42" in text
        assert "status=claimed" in text

    async def test_already_refunded_idempotent(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_refund_lot(output=_success_output(was_already=True))
        await dispatch_refund_lot(
            result=_verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(refund_lot=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-already-refunded" in text
        assert "lot_id=42" in text
        assert "pool_after=15000000" in text

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_refund_lot(output=_success_output())
        await dispatch_refund_lot(
            result=_verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(refund_lot=uc),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-refund-lot-success" in text
        assert "lot_id=42" in text
        assert "currency=ton" in text
        assert "amount=5000000" in text
        assert "pool_after=15000000" in text

        # Контракт `RefundLotInput`-вызова: lot_id и reason приходят из
        # payload, actor_tg_id и tg_chat_id — из identity.
        uc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = uc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.lot_id == 42
        assert call_input.reason == "stuck reservation"
        assert call_input.actor_tg_id == 42
        assert call_input.tg_chat_id == 42
