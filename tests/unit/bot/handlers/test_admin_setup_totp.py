"""Unit-тесты handler-а `/admin_setup_totp` (Спринт 2.5-D.6, ГДД §18.6.5).

Проверяет все ветки `handle_admin_setup_totp`:
- non-private-чат → ответ-предупреждение, use-case не вызывается;
- пустой `/admin_setup_totp` без аргумента → usage-локаль, use-case не вызывается;
- AuthorizationError / AdminAuthorizationDeniedError → not-authorized-локаль;
- BootstrapPasswordNotConfiguredError → password-not-configured-локаль;
- BootstrapPasswordInvalidError → password-invalid-локаль;
- TotpAlreadyConfiguredError → already-configured-локаль;
- happy-path: secret + provisioning_uri попадают в structlog (НЕ в чат),
  в чат уходит только локализованный success.

Сам use-case (`SetupAdminTotp`) подменяется `MagicMock(spec=...)`-фейком —
все ветки use-case-а покрыты `tests/unit/application/admin/test_setup_totp.py`.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    SetupAdminTotp,
    SetupAdminTotpOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_setup_totp import handle_admin_setup_totp
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import (
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    AdminRole,
    BootstrapPasswordInvalidError,
    BootstrapPasswordNotConfiguredError,
    TotpAlreadyConfiguredError,
)

_RU = Locale("ru")
_FAKE_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
_FAKE_URI = (
    "otpauth://totp/Pipirik%20Wars%3Aadmin_7?"
    f"secret={_FAKE_SECRET}&issuer=Pipirik%20Wars&algorithm=SHA1&digits=6&period=30"
)


class _StubBundle(IMessageBundle):
    """Mини-бандл, отдающий `key|locale|kw1=v1,...` для assert-ов."""

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
    return CommandObject(prefix="/", command="admin_setup_totp", mention=None, args=args)


def _stub_setup_totp(
    *,
    output: SetupAdminTotpOutput | None = None,
    raises: Exception | None = None,
) -> SetupAdminTotp:
    fake = MagicMock(spec=SetupAdminTotp)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock(
            return_value=SetupAdminTotpOutput(secret=_FAKE_SECRET, provisioning_uri=_FAKE_URI),
        )
    return cast(SetupAdminTotp, fake)


@pytest.mark.asyncio
class TestHandleAdminSetupTotpGuards:
    """Контроль не-private-чата и пустого аргумента."""

    async def test_non_private_chat_replies_localized_hint(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command("password"),
            tg_identity=_identity(chat_kind="group"),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-setup-totp-non-private" in msg.answer.await_args.args[0]
        # Use-case не вызывался — пароль не должен утечь.
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_non_private(self, bundle: IMessageBundle) -> None:
        """Если middleware не подкинул `tg_identity` (странная ситуация),
        идём по non-private-ветке — fail-closed: пароль не передаётся в use-case."""
        msg = _msg_mock()
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command("password"),
            tg_identity=None,
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-setup-totp-non-private" in msg.answer.await_args.args[0]
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_no_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-setup-totp-usage" in msg.answer.await_args.args[0]
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_whitespace_only_args_replies_usage(self, bundle: IMessageBundle) -> None:
        """`/admin_setup_totp    ` (только пробелы) — тоже usage."""
        msg = _msg_mock()
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command("   "),
            tg_identity=_identity(),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-setup-totp-usage" in msg.answer.await_args.args[0]
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_locale_defaults_when_none(self, bundle: IMessageBundle) -> None:
        """Если `locale=None` (middleware не подкинул) — используем `DEFAULT_LOCALE`."""
        msg = _msg_mock()
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=None,
        )

        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-setup-totp-usage" in rendered
        # DEFAULT_LOCALE — `en` (см. application/i18n/locale.py).
        assert f"|{DEFAULT_LOCALE.code}|" in rendered


@pytest.mark.asyncio
class TestHandleAdminSetupTotpErrors:
    """Все ветки исключений use-case-а → локализованные ответы."""

    @pytest.mark.parametrize(
        ("error", "expected_key"),
        [
            (
                AuthorizationError(requirement="active-admin", detail="inactive"),
                "admin-setup-totp-not-authorized",
            ),
            (
                AdminAuthorizationDeniedError(
                    command_kind=AdminCommandKind.SETUP_TOTP,
                    actor_role=AdminRole.ECONOMIST,
                    detail="rbac",
                ),
                "admin-setup-totp-not-authorized",
            ),
            (
                BootstrapPasswordNotConfiguredError(),
                "admin-setup-totp-password-not-configured",
            ),
            (
                BootstrapPasswordInvalidError(),
                "admin-setup-totp-password-invalid",
            ),
            (
                TotpAlreadyConfiguredError(),
                "admin-setup-totp-already-configured",
            ),
        ],
    )
    async def test_use_case_error_renders_specific_locale(
        self,
        bundle: IMessageBundle,
        error: Exception,
        expected_key: str,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_setup_totp(raises=error)

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command("password"),
            tg_identity=_identity(),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert expected_key in rendered

    async def test_unknown_use_case_exception_propagates(self, bundle: IMessageBundle) -> None:
        """Неожиданные исключения handler не глотает — они падают наружу
        и попадают в общий error-middleware bot-а."""
        msg = _msg_mock()
        uc = _stub_setup_totp(raises=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await handle_admin_setup_totp(
                message=cast(Message, msg),
                command=_command("password"),
                tg_identity=_identity(),
                setup_admin_totp=uc,
                bundle=bundle,
                locale=_RU,
            )
        # До локализованного ответа не дошли.
        msg.answer.assert_not_awaited()


@pytest.mark.asyncio
class TestHandleAdminSetupTotpHappyPath:
    """Успешный путь: вызов use-case, лог в structlog, success в чат."""

    async def test_success_passes_input_calls_logger_and_answers(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_setup_totp()
        # Перехватываем structlog-вывод через `LogCapture`-процессор —
        # это единственный надёжный способ assert-ить структурированные
        # поля event, secret, provisioning_uri (stdlib `caplog` не видит
        # structlog по умолчанию, см. tests/unit/infrastructure/dau/test_alert.py).
        cap = structlog.testing.LogCapture()
        structlog.configure(processors=[cap])
        try:
            await handle_admin_setup_totp(
                message=cast(Message, msg),
                command=_command("correct horse battery staple"),
                tg_identity=_identity(tg_user_id=7),
                setup_admin_totp=uc,
                bundle=bundle,
                locale=_RU,
            )
        finally:
            structlog.reset_defaults()

        # 1. Use-case вызван с распарсенным паролем + актуальным tg-id.
        uc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        call = uc.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert call.actor_tg_id == 7
        assert call.password == "correct horse battery staple"
        assert call.tg_chat_id == 42

        # 2. В чат уходит ровно одно сообщение — локализованный success-текст.
        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-setup-totp-success" in rendered
        # Ни секрет, ни provisioning_uri в чат-ответ НЕ просачиваются.
        assert _FAKE_SECRET not in rendered
        assert _FAKE_URI not in rendered

        # 3. structlog логирует event="admin_totp_setup" с secret и URI —
        # это единственное место, где они оказываются в логах.
        setup_entries = [e for e in cap.entries if e.get("event") == "admin_totp_setup"]
        assert len(setup_entries) == 1
        entry = setup_entries[0]
        assert entry["log_level"] == "info"
        assert entry["actor_tg_id"] == 7
        assert entry["secret"] == _FAKE_SECRET
        assert entry["provisioning_uri"] == _FAKE_URI

    async def test_success_password_with_spaces_passed_verbatim(
        self,
        bundle: IMessageBundle,
    ) -> None:
        """Пароли с пробелами (passphrase-style) идут в use-case как-есть."""
        msg = _msg_mock()
        uc = _stub_setup_totp()

        await handle_admin_setup_totp(
            message=cast(Message, msg),
            command=_command("  multi word passphrase  "),
            tg_identity=_identity(),
            setup_admin_totp=uc,
            bundle=bundle,
            locale=_RU,
        )

        uc.execute.assert_awaited_once()  # type: ignore[attr-defined]
        # `.strip()` снимает только внешние пробелы, внутренние сохраняются.
        assert uc.execute.await_args.args[0].password == "multi word passphrase"  # type: ignore[attr-defined]
