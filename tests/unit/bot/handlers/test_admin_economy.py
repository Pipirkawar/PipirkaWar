"""Unit-тесты handler-ов и dispatch-функций admin_economy (Спринт 2.5-C).

Покрывает:
- handle_grant_length / handle_grant_thickness / handle_balance_get /
  handle_balance_set (фаза 1 — выдача `/confirm`-токена или read-only).
- dispatch_grant_length / dispatch_grant_thickness / dispatch_balance_set
  (фаза 2 — после успешной TOTP-проверки).
- CONFIRM_DISPATCHERS-registry: правильный роутинг по `command_kind`.
- idempotency-replay: `was_idempotent_replay=True` → IdempotencyReplayPresenter.
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
    BalanceKeyError,
    BanPlayer,
    GetBalanceValue,
    GetBalanceValueOutput,
    GrantLength,
    GrantLengthBlockedError,
    GrantLengthOutput,
    GrantThickness,
    GrantThicknessBlockedError,
    GrantThicknessOutput,
    IBroadcastTaskSpawner,
    RequestAdminConfirm,
    RequestAdminConfirmOutput,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    SetBalanceValueOutput,
    ThicknessLevelInvalidError,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import RefundLot
from pipirik_wars.bot.handlers.admin_economy import (
    COMMAND_KIND_BALANCE_SET,
    COMMAND_KIND_GRANT_LENGTH,
    COMMAND_KIND_GRANT_THICKNESS,
    CONFIRM_DISPATCHERS,
    REPLY_NON_PRIVATE_RU,
    ConfirmDispatchDeps,
    dispatch_balance_set,
    dispatch_grant_length,
    dispatch_grant_thickness,
    handle_balance_get,
    handle_balance_set,
    handle_grant_length,
    handle_grant_thickness,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.errors import (
    AnticheatSoftBanError,
    LengthDeltaInvalidError,
)
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.shared.errors import ConfigError

_RU = Locale("ru")


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


class _StubBundle(IMessageBundle):
    def format(self, key: MessageKey, *, locale: Locale, **kwargs: object) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


def _stub_request_confirm(
    *, output: RequestAdminConfirmOutput | None = None
) -> RequestAdminConfirm:
    fake = MagicMock(spec=RequestAdminConfirm)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(RequestAdminConfirm, fake)


def _stub_grant_length(*, output: GrantLengthOutput | None = None) -> GrantLength:
    fake = MagicMock(spec=GrantLength)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(GrantLength, fake)


def _stub_grant_thickness(*, output: GrantThicknessOutput | None = None) -> GrantThickness:
    fake = MagicMock(spec=GrantThickness)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(GrantThickness, fake)


def _stub_get_balance(*, output: GetBalanceValueOutput | None = None) -> GetBalanceValue:
    fake = MagicMock(spec=GetBalanceValue)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(GetBalanceValue, fake)


def _stub_set_balance(*, output: SetBalanceValueOutput | None = None) -> SetBalanceValue:
    fake = MagicMock(spec=SetBalanceValue)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(SetBalanceValue, fake)


def _fixed_clock() -> IClock:
    fake = MagicMock(spec=IClock)
    fake.now = MagicMock(return_value=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    return cast(IClock, fake)


def _confirm_token() -> RequestAdminConfirmOutput:
    return RequestAdminConfirmOutput(token="TOK", ttl_seconds=120)


# ── /grant_length фаза 1 ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandleGrantLength:
    async def test_non_private(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 5 reason"),
            tg_identity=_identity(chat_kind="group"),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_empty_args(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", ""),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-usage" in msg.answer.await_args.args[0]

    async def test_one_arg(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-usage" in msg.answer.await_args.args[0]

    async def test_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "abc 5 reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-bad-id" in msg.answer.await_args.args[0]

    async def test_bad_delta(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 abc reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-bad-delta" in msg.answer.await_args.args[0]

    async def test_zero_delta(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 0 reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-bad-delta" in msg.answer.await_args.args[0]

    async def test_no_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 5"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-no-reason" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(side_effect=AuthorizationError(requirement="x", detail="y"))  # type: ignore[method-assign]
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 5 reason"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-not-authorized" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm()
        rc.execute = AsyncMock(side_effect=TotpNotConfiguredError("no"))  # type: ignore[method-assign]
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 5 reason"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-length-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_grant_length(
            message=cast(Message, msg),
            command=_command("grant_length", "100 5 buff"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-length-confirm-issued" in text
        assert "token=TOK" in text
        rc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_GRANT_LENGTH
        assert call_input.target_id == "100"
        assert call_input.payload["target_tg_id"] == 100
        assert call_input.payload["delta_cm"] == 5
        assert call_input.payload["reason"] == "buff"


# ── /grant_thickness фаза 1 ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandleGrantThickness:
    async def test_non_private(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", "100 3 reason"),
            tg_identity=_identity(chat_kind="group"),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", ""),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-thickness-usage" in msg.answer.await_args.args[0]

    async def test_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", "abc 3 reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-thickness-bad-id" in msg.answer.await_args.args[0]

    async def test_bad_level(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", "100 zzz reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-thickness-bad-level" in msg.answer.await_args.args[0]

    async def test_no_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", "100 3"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-grant-thickness-no-reason" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_grant_thickness(
            message=cast(Message, msg),
            command=_command("grant_thickness", "100 4 promote"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-thickness-confirm-issued" in text
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_GRANT_THICKNESS
        assert call_input.payload["new_level"] == 4


# ── /balance_get (read-only, без TOTP) ──────────────────────────────────────


@pytest.mark.asyncio
class TestHandleBalanceGet:
    async def test_non_private(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        await handle_balance_get(
            message=cast(Message, msg),
            command=_command("balance_get", "key"),
            tg_identity=_identity(chat_kind="group"),
            get_balance_value=_stub_get_balance(),
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_balance_get(
            message=cast(Message, msg),
            command=_command("balance_get", ""),
            tg_identity=_identity(),
            get_balance_value=_stub_get_balance(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-balance-get-usage" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gb = _stub_get_balance()
        gb.execute = AsyncMock(side_effect=AuthorizationError(requirement="x", detail="y"))  # type: ignore[method-assign]
        await handle_balance_get(
            message=cast(Message, msg),
            command=_command("balance_get", "forest.cooldown_min_minutes"),
            tg_identity=_identity(),
            get_balance_value=gb,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-balance-get-not-authorized" in msg.answer.await_args.args[0]

    async def test_key_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gb = _stub_get_balance()
        gb.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=BalanceKeyError(
                key="no.such.key",
                segment="no",
                reason="missing_attribute",
            ),
        )
        await handle_balance_get(
            message=cast(Message, msg),
            command=_command("balance_get", "no.such.key"),
            tg_identity=_identity(),
            get_balance_value=gb,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-balance-get-key-not-found" in text
        assert "path=no.such.key" in text

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gb = _stub_get_balance(
            output=GetBalanceValueOutput(key="forest.x", raw_value=42, balance_version=7),
        )
        await handle_balance_get(
            message=cast(Message, msg),
            command=_command("balance_get", "forest.x"),
            tg_identity=_identity(),
            get_balance_value=gb,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-balance-get-result" in text
        assert "path=forest.x" in text
        assert "version=7" in text


# ── /balance_set фаза 1 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandleBalanceSet:
    async def test_non_private(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", "key 1 reason"),
            tg_identity=_identity(chat_kind="group"),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", ""),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-balance-set-usage" in msg.answer.await_args.args[0]

    async def test_two_args_returns_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", "key 5"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-balance-set-usage" in msg.answer.await_args.args[0]

    async def test_bad_value(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", "key not_json reason"),
            tg_identity=_identity(),
            request_admin_confirm=_stub_request_confirm(),
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-balance-set-bad-value" in msg.answer.await_args.args[0]

    async def test_confirm_issued_with_int(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", "forest.x 42 tweak"),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-balance-set-confirm-issued" in text
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.command_kind == COMMAND_KIND_BALANCE_SET
        assert call_input.payload["key"] == "forest.x"
        assert call_input.payload["value"] == 42

    async def test_confirm_issued_with_json_object(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        rc = _stub_request_confirm(output=_confirm_token())
        await handle_balance_set(
            message=cast(Message, msg),
            command=_command("balance_set", 'k {"a":1} tweak'),
            tg_identity=_identity(),
            request_admin_confirm=rc,
            bundle=bundle,
            locale=_RU,
        )
        call_input = rc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call_input.payload["value"] == {"a": 1}


# ── dispatch-функции (фаза 2) ───────────────────────────────────────────────


def _verify_output_grant_length(
    *, target_tg_id: int = 100, delta_cm: int = 5
) -> VerifyAdminConfirmOutput:
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_GRANT_LENGTH,
        target_kind="player",
        target_id=str(target_tg_id),
        payload=MappingProxyType(
            {"target_tg_id": target_tg_id, "delta_cm": delta_cm, "reason": "buff"},
        ),
    )


def _verify_output_grant_thickness(
    *, target_tg_id: int = 100, new_level: int = 4
) -> VerifyAdminConfirmOutput:
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_GRANT_THICKNESS,
        target_kind="player",
        target_id=str(target_tg_id),
        payload=MappingProxyType(
            {"target_tg_id": target_tg_id, "new_level": new_level, "reason": "promote"},
        ),
    )


def _verify_output_balance_set(
    *, key: str = "forest.x", value: object = 42
) -> VerifyAdminConfirmOutput:
    return VerifyAdminConfirmOutput(
        command_kind=COMMAND_KIND_BALANCE_SET,
        target_kind="balance_key",
        target_id=key,
        payload=MappingProxyType({"key": key, "value": value, "reason": "tweak"}),
    )


def _stub_ban_player() -> BanPlayer:
    return MagicMock(spec=BanPlayer)


def _stub_run_broadcast() -> RunBroadcastAnnouncement:
    fake = MagicMock(spec=RunBroadcastAnnouncement)
    fake.execute = AsyncMock()
    return cast(RunBroadcastAnnouncement, fake)


def _stub_broadcast_task_spawner() -> IBroadcastTaskSpawner:
    fake = MagicMock(spec=IBroadcastTaskSpawner)
    return cast(IBroadcastTaskSpawner, fake)


def _stub_refund_lot() -> RefundLot:
    fake = MagicMock(spec=RefundLot)
    fake.execute = AsyncMock()
    return cast(RefundLot, fake)


def _deps(
    *,
    grant_length: GrantLength | None = None,
    grant_thickness: GrantThickness | None = None,
    set_balance: SetBalanceValue | None = None,
    ban_player: BanPlayer | None = None,
) -> ConfirmDispatchDeps:
    return ConfirmDispatchDeps(
        grant_length=grant_length or _stub_grant_length(),
        grant_thickness=grant_thickness or _stub_grant_thickness(),
        set_balance_value=set_balance or _stub_set_balance(),
        ban_player=ban_player or _stub_ban_player(),
        run_broadcast_announcement=_stub_run_broadcast(),
        broadcast_task_spawner=_stub_broadcast_task_spawner(),
        clock=_fixed_clock(),
        refund_lot=_stub_refund_lot(),
    )


@pytest.mark.asyncio
class TestDispatchGrantLength:
    async def test_payload_invalid(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        result = VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_GRANT_LENGTH,
            target_kind="player",
            target_id="100",
            payload=MappingProxyType({"target_tg_id": "not-int"}),
        )
        await dispatch_grant_length(
            result=result,
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_player_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length()
        gl.execute = AsyncMock(side_effect=PlayerNotFoundError(tg_id=100))  # type: ignore[method-assign]
        await dispatch_grant_length(
            result=_verify_output_grant_length(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        assert "admin-grant-length-not-found" in msg.answer.await_args.args[0]

    async def test_blocked(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length()
        gl.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=GrantLengthBlockedError(tg_id=100, reason="banned"),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-length-blocked" in text
        assert "reason=banned" in text

    async def test_soft_ban(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length()
        gl.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AnticheatSoftBanError(
                tg_id=100, banned_until=datetime(2026, 5, 9, tzinfo=UTC)
            ),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        assert "admin-grant-length-soft-ban" in msg.answer.await_args.args[0]

    async def test_bad_delta_from_domain(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length()
        gl.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=LengthDeltaInvalidError(
                delta_cm=999, source="admin_grant", reason_code="other"
            ),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(delta_cm=999),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        assert "admin-grant-length-bad-delta" in msg.answer.await_args.args[0]

    async def test_idempotent_replay(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length(
            output=GrantLengthOutput(
                target_tg_id=100,
                applied_delta_cm=0,
                clamped_from=None,
                triggered_soft_ban=False,
                new_length_cm=100,
                was_idempotent_replay=True,
            ),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-idempotency-replay" in text
        assert f"command_kind={COMMAND_KIND_GRANT_LENGTH}" in text

    async def test_clamped(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length(
            output=GrantLengthOutput(
                target_tg_id=100,
                applied_delta_cm=10,
                clamped_from=50,
                triggered_soft_ban=False,
                new_length_cm=110,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(delta_cm=50),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-length-success-clamped" in text
        assert "applied=10" in text
        assert "requested=50" in text

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gl = _stub_grant_length(
            output=GrantLengthOutput(
                target_tg_id=100,
                applied_delta_cm=5,
                clamped_from=None,
                triggered_soft_ban=False,
                new_length_cm=105,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_grant_length(
            result=_verify_output_grant_length(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_length=gl),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-length-success" in text
        assert "new_length_cm=105" in text


@pytest.mark.asyncio
class TestDispatchGrantThickness:
    async def test_payload_invalid(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        result = VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_GRANT_THICKNESS,
            target_kind="player",
            target_id="100",
            payload=MappingProxyType({"target_tg_id": 100}),
        )
        await dispatch_grant_thickness(
            result=result,
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_blocked(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gt = _stub_grant_thickness()
        gt.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=GrantThicknessBlockedError(tg_id=100, reason="banned"),
        )
        await dispatch_grant_thickness(
            result=_verify_output_grant_thickness(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_thickness=gt),
        )
        assert "admin-grant-thickness-blocked" in msg.answer.await_args.args[0]

    async def test_level_invalid(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gt = _stub_grant_thickness()
        gt.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=ThicknessLevelInvalidError(level=99, max_level=10, reason_code="above_max"),
        )
        await dispatch_grant_thickness(
            result=_verify_output_grant_thickness(new_level=99),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_thickness=gt),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-thickness-level-invalid" in text
        assert "max_level=10" in text

    async def test_already_at_level(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gt = _stub_grant_thickness(
            output=GrantThicknessOutput(
                target_tg_id=100,
                previous_level=4,
                new_level=4,
                was_already_at_level=True,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_grant_thickness(
            result=_verify_output_grant_thickness(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_thickness=gt),
        )
        assert "admin-grant-thickness-already-at-level" in msg.answer.await_args.args[0]

    async def test_idempotent_replay(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gt = _stub_grant_thickness(
            output=GrantThicknessOutput(
                target_tg_id=100,
                previous_level=4,
                new_level=4,
                was_already_at_level=False,
                was_idempotent_replay=True,
            ),
        )
        await dispatch_grant_thickness(
            result=_verify_output_grant_thickness(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_thickness=gt),
        )
        assert "admin-idempotency-replay" in msg.answer.await_args.args[0]

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        gt = _stub_grant_thickness(
            output=GrantThicknessOutput(
                target_tg_id=100,
                previous_level=3,
                new_level=4,
                was_already_at_level=False,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_grant_thickness(
            result=_verify_output_grant_thickness(new_level=4),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(grant_thickness=gt),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-grant-thickness-success" in text
        assert "new_level=4" in text


@pytest.mark.asyncio
class TestDispatchBalanceSet:
    async def test_payload_invalid(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        result = VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_BALANCE_SET,
            target_kind="balance_key",
            target_id="forest.x",
            payload=MappingProxyType({"key": "forest.x"}),
        )
        await dispatch_balance_set(
            result=result,
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(),
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]

    async def test_key_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        sb = _stub_set_balance()
        sb.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=BalanceKeyError(key="x", segment="x", reason="missing"),
        )
        await dispatch_balance_set(
            result=_verify_output_balance_set(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(set_balance=sb),
        )
        assert "admin-balance-set-key-not-found" in msg.answer.await_args.args[0]

    async def test_validation_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        sb = _stub_set_balance()
        sb.execute = AsyncMock(side_effect=ConfigError("expected int"))  # type: ignore[method-assign]
        await dispatch_balance_set(
            result=_verify_output_balance_set(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(set_balance=sb),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-balance-set-validation-error" in text
        assert "error=expected int" in text

    async def test_already_at_value(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        sb = _stub_set_balance(
            output=SetBalanceValueOutput(
                key="forest.x",
                previous_raw_value=42,
                new_raw_value=42,
                new_balance_version=7,
                was_already_at_value=True,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_balance_set(
            result=_verify_output_balance_set(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(set_balance=sb),
        )
        assert "admin-balance-set-already-at-value" in msg.answer.await_args.args[0]

    async def test_idempotent_replay(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        sb = _stub_set_balance(
            output=SetBalanceValueOutput(
                key="forest.x",
                previous_raw_value=42,
                new_raw_value=42,
                new_balance_version=7,
                was_already_at_value=False,
                was_idempotent_replay=True,
            ),
        )
        await dispatch_balance_set(
            result=_verify_output_balance_set(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(set_balance=sb),
        )
        assert "admin-idempotency-replay" in msg.answer.await_args.args[0]

    async def test_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        sb = _stub_set_balance(
            output=SetBalanceValueOutput(
                key="forest.x",
                previous_raw_value=10,
                new_raw_value=42,
                new_balance_version=8,
                was_already_at_value=False,
                was_idempotent_replay=False,
            ),
        )
        await dispatch_balance_set(
            result=_verify_output_balance_set(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=_deps(set_balance=sb),
        )
        text = msg.answer.await_args.args[0]
        assert "admin-balance-set-success" in text
        assert "version=8" in text


# ── CONFIRM_DISPATCHERS registry ────────────────────────────────────────────


class TestConfirmDispatchersRegistry:
    def test_registry_has_all_three(self) -> None:
        assert COMMAND_KIND_GRANT_LENGTH in CONFIRM_DISPATCHERS
        assert COMMAND_KIND_GRANT_THICKNESS in CONFIRM_DISPATCHERS
        assert COMMAND_KIND_BALANCE_SET in CONFIRM_DISPATCHERS
        assert CONFIRM_DISPATCHERS[COMMAND_KIND_GRANT_LENGTH] is dispatch_grant_length
        assert CONFIRM_DISPATCHERS[COMMAND_KIND_GRANT_THICKNESS] is dispatch_grant_thickness
        assert CONFIRM_DISPATCHERS[COMMAND_KIND_BALANCE_SET] is dispatch_balance_set
