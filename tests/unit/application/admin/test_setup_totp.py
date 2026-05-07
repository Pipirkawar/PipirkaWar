"""Unit-тесты `SetupAdminTotp` (Спринт 2.5-D.6, ГДД §18.6.5).

Use-case делает self-service выдачу TOTP-секрета super-admin-у. Здесь
проверяем все ветки execute(): RBAC-deny, password-not-configured,
password-invalid, already-configured, success-case с записью аудита и
сохранением секрета в репо.

Реальный `pyotp` не вызываем — генератор подменяется фейком, чтобы
тесты были детерминированы и не зависели от криптослучайности.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    PROVISIONING_ALGORITHM,
    PROVISIONING_DIGITS,
    PROVISIONING_ISSUER,
    PROVISIONING_PERIOD,
    SetupAdminTotp,
    SetupAdminTotpInput,
    build_provisioning_uri,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    AdminRole,
    BootstrapPasswordInvalidError,
    BootstrapPasswordNotConfiguredError,
    ITotpSecretGenerator,
    TotpAlreadyConfiguredError,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzMatrix
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
_BOOTSTRAP_PASSWORD = "correct horse battery staple"
_FAKE_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # 32 BASE32-символа


@dataclass
class _FakeSecretGenerator(ITotpSecretGenerator):
    """Возвращает фиксированный BASE32-секрет; считает вызовы."""

    secret: str = _FAKE_SECRET
    calls: int = 0

    def generate(self) -> str:
        self.calls += 1
        return self.secret


def _build(
    *,
    bootstrap_password: str | None = _BOOTSTRAP_PASSWORD,
    authz_allow_all: bool = True,
) -> tuple[
    SetupAdminTotp,
    FakeAdminRepository,
    FakeAdminAuditLogger,
    _FakeSecretGenerator,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    audit = FakeAdminAuditLogger()
    generator = _FakeSecretGenerator()
    uow = FakeUnitOfWork()
    authz = (
        FakeAdminAuthzAllowAll()
        if authz_allow_all
        else FakeAdminAuthzMatrix(allow={AdminCommandKind.SETUP_TOTP: False})
    )
    use_case = SetupAdminTotp(
        uow=uow,
        admins=admins,
        audit=audit,
        clock=FakeClock(_NOW),
        authz=authz,
        secret_generator=generator,
        bootstrap_password=bootstrap_password,
    )
    return use_case, admins, audit, generator, uow


@pytest.mark.asyncio
class TestSetupAdminTotp:
    async def test_unknown_actor_raises_authorization_error(self) -> None:
        uc, _, _, generator, uow = _build()

        with pytest.raises(AuthorizationError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password=_BOOTSTRAP_PASSWORD),
            )
        assert generator.calls == 0
        assert uow.commits == 0

    async def test_inactive_admin_raises_authorization_error(self) -> None:
        uc, admins, _, generator, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password=_BOOTSTRAP_PASSWORD),
            )
        assert generator.calls == 0
        assert uow.commits == 0

    async def test_rbac_deny_raises_admin_authorization_denied(self) -> None:
        """`ECONOMIST` не имеет права на `SETUP_TOTP` — `SUPER_ADMIN`-only."""
        uc, admins, audit, generator, uow = _build(authz_allow_all=False)
        admins.seed(tg_id=42, role=AdminRole.ECONOMIST)

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password=_BOOTSTRAP_PASSWORD),
            )
        assert generator.calls == 0
        # Запись `ADMIN_AUTHORIZATION_DENIED` должна быть в аудите.
        assert any(
            entry.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED for entry in audit.entries
        )
        # `ensure_admin_authorized` открывает свой короткий UoW для записи
        # денайл-аудита (commit=1); main-UoW внутри execute() при отказе
        # уже не открывается, поэтому `set_totp_secret` тоже не вызывался —
        # admin.totp_secret остался `None`.
        assert uow.commits == 1
        assert admins.rows[0].totp_secret is None
        # Запись `ADMIN_TOTP_SETUP` НЕ должна попасть в аудит.
        assert not any(entry.action is AdminAuditAction.ADMIN_TOTP_SETUP for entry in audit.entries)

    async def test_password_not_configured_raises_fail_closed(self) -> None:
        uc, admins, _, generator, uow = _build(bootstrap_password=None)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(BootstrapPasswordNotConfiguredError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password="anything"),
            )
        assert generator.calls == 0
        assert uow.commits == 0

    async def test_password_mismatch_raises_invalid(self) -> None:
        uc, admins, _, generator, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(BootstrapPasswordInvalidError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password="wrong-password"),
            )
        assert generator.calls == 0
        assert uow.commits == 0

    async def test_already_configured_raises_no_overwrite(self) -> None:
        uc, admins, _, generator, uow = _build()
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="EXISTINGSECRET234567",
        )

        with pytest.raises(TotpAlreadyConfiguredError):
            await uc.execute(
                SetupAdminTotpInput(actor_tg_id=42, password=_BOOTSTRAP_PASSWORD),
            )
        # Существующий секрет не должен быть переписан.
        assert admins.rows[0].totp_secret == "EXISTINGSECRET234567"
        assert generator.calls == 0
        assert uow.commits == 0

    async def test_success_writes_secret_audit_and_returns_uri(self) -> None:
        uc, admins, audit, generator, uow = _build()
        admin = admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        out = await uc.execute(
            SetupAdminTotpInput(
                actor_tg_id=42,
                password=_BOOTSTRAP_PASSWORD,
                tg_chat_id=987654,
            ),
        )

        # 1. Сгенерированный секрет ушёл в репо.
        assert generator.calls == 1
        assert out.secret == _FAKE_SECRET
        assert admins.rows[0].totp_secret == _FAKE_SECRET

        # 2. provisioning_uri собран корректно.
        assert out.provisioning_uri.startswith("otpauth://totp/")
        assert f"secret={_FAKE_SECRET}" in out.provisioning_uri
        assert f"algorithm={PROVISIONING_ALGORITHM}" in out.provisioning_uri
        assert f"digits={PROVISIONING_DIGITS}" in out.provisioning_uri
        assert f"period={PROVISIONING_PERIOD}" in out.provisioning_uri
        # account_name = "admin_<id>".
        assert f"admin_{admin.id}" in out.provisioning_uri

        # 3. Audit-запись содержит ровно одну `ADMIN_TOTP_SETUP`-строку.
        setup_entries = [e for e in audit.entries if e.action is AdminAuditAction.ADMIN_TOTP_SETUP]
        assert len(setup_entries) == 1
        entry = setup_entries[0]
        assert entry.admin_id == admin.id
        assert entry.target_kind == "admin"
        assert entry.target_id == str(admin.id)
        # Сам секрет в audit-лог не пишется (политика D.6).
        assert entry.before is None
        assert entry.after is None
        assert entry.idempotency_key is None
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == 987654

        # 4. main-UoW коммитнут ровно один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0


def test_provisioning_uri_format_matches_rfc6238() -> None:
    uri = build_provisioning_uri(secret="ABC123", account_name="admin_42")
    # Формат: otpauth://totp/<label>?secret=<base32>&issuer=<issuer>&algorithm=...
    assert uri.startswith("otpauth://totp/")
    # `Pipirik Wars:admin_42` — label, в URL-encoded виде.
    assert "Pipirik%20Wars%3Aadmin_42" in uri
    assert "secret=ABC123" in uri
    assert "issuer=Pipirik%20Wars" in uri
    assert "algorithm=SHA1" in uri
    assert "digits=6" in uri
    assert "period=30" in uri


def test_provisioning_constants_match_rfc6238_defaults() -> None:
    """Защита от случайного дрейфа констант: они влияют на TOTP-совместимость."""
    assert PROVISIONING_ISSUER == "Pipirik Wars"
    assert PROVISIONING_ALGORITHM == "SHA1"
    assert PROVISIONING_DIGITS == 6
    assert PROVISIONING_PERIOD == 30
