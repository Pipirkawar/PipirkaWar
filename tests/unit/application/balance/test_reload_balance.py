"""Unit-тесты `ReloadBalance` (Спринт 1.1.E, ГДД §2.3 / §18.6.5).

Покрываем:

1. Активный super_admin → reload проходит, аудит-запись создана,
   возвращены `version_before` / `version_after` корректно.
2. Активный economist (тоже разрешён) → проходит.
3. Не админ (нет в таблице) → `AuthorizationError`, reload НЕ зовётся.
4. Активный support / read_only (не имеют `can_write_balance`) →
   `AuthorizationError`.
5. Деактивированный super_admin → `AuthorizationError`.
6. Невалидный YAML после reload → пробрасывается `ConfigError`,
   аудит **не** пишется (нет state change).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.domain.admin import (
    AdminAuthorizationDeniedError,
    AdminRole,
    RoleBasedAdminAuthorizationPolicy,
)
from pipirik_wars.domain.balance import IBalanceReloader
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.shared.errors import ConfigError
from tests.fakes import (
    FakeAdminAuditLogger,
    FakeAdminRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import valid_balance_payload


def _build_balance_with_version(version: int, name: str = "Пипирик") -> BalanceConfig:
    payload = valid_balance_payload()
    payload["version"] = version
    payload["display_names"] = [{"from": 0, "to": None, "name": name}]
    return BalanceConfig.model_validate(payload)


def _build(
    *,
    initial_version: int = 1,
) -> tuple[
    ReloadBalance,
    FakeAdminRepository,
    FakeBalanceConfig,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeAdminAuditLogger,
]:
    uow = FakeUnitOfWork()
    audit = FakeAuditLogger()
    admin_audit = FakeAdminAuditLogger()
    admins = FakeAdminRepository()
    balance = FakeBalanceConfig(_build_balance_with_version(initial_version))
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    use_case = ReloadBalance(
        uow=uow,
        admins=admins,
        balance=balance,
        reloader=balance,
        audit=audit,
        admin_audit=admin_audit,
        authz=RoleBasedAdminAuthorizationPolicy(),
        clock=clock,
    )
    return use_case, admins, balance, audit, uow, clock, admin_audit


@pytest.mark.asyncio
class TestAuthorization:
    async def test_super_admin_can_reload(self) -> None:
        use_case, admins, balance, audit, _, _, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        balance.queue_next_reload(_build_balance_with_version(2))

        result = await use_case.execute(actor_tg_id=42)

        assert result.version_before == 1
        assert result.version_after == 2
        assert len(audit.entries) == 1

    async def test_economist_can_reload(self) -> None:
        use_case, admins, balance, audit, _, _, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.ECONOMIST)
        balance.queue_next_reload(_build_balance_with_version(2))

        result = await use_case.execute(actor_tg_id=42)

        assert result.version_after == 2
        assert len(audit.entries) == 1

    async def test_unknown_user_raises_authorization_error(self) -> None:
        use_case, _, balance, audit, _, _, _ = _build()
        # Никого не подкладывали — repo админов пуст.

        with pytest.raises(AuthorizationError) as exc_info:
            await use_case.execute(actor_tg_id=42)

        assert exc_info.value.requirement == "admin_balance_write"
        # Reload не должен был случиться.
        assert balance.get().version == 1
        assert audit.entries == []

    async def test_support_role_cannot_reload_balance(self) -> None:
        # Спринт 2.5-D.7: support — по RBAC-матрице D.8 RELOAD_BALANCE
        # доступен только super_admin+economist; попытка эскалации фиксируется
        # в admin_audit как `ADMIN_AUTHORIZATION_DENIED`.
        use_case, admins, balance, audit, _, _, admin_audit = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(AdminAuthorizationDeniedError):
            await use_case.execute(actor_tg_id=42)

        assert balance.get().version == 1
        assert audit.entries == []
        assert len(admin_audit.entries) == 1
        assert admin_audit.entries[0].action.value == "admin_authorization_denied"

    async def test_read_only_admin_cannot_reload_balance(self) -> None:
        use_case, admins, _, audit, _, _, admin_audit = _build()
        admins.seed(tg_id=42, role=AdminRole.READ_ONLY)

        with pytest.raises(AdminAuthorizationDeniedError):
            await use_case.execute(actor_tg_id=42)

        assert audit.entries == []
        assert len(admin_audit.entries) == 1

    async def test_deactivated_super_admin_cannot_reload(self) -> None:
        # Inactive-admin отбивается defense-in-depth-проверкой в use-case-е
        # до RBAC — поэтому admin_audit пуст (мы не светим деактивацию
        # через audit-лог: это ответственность системы admin-management).
        use_case, admins, _, audit, _, _, admin_audit = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        admins.deactivate(tg_id=42)

        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=42)

        assert audit.entries == []
        assert admin_audit.entries == []


@pytest.mark.asyncio
class TestReload:
    async def test_audit_entry_contains_versions_and_actor(self) -> None:
        use_case, admins, balance, audit, uow, clock, _ = _build()
        admin = admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        balance.queue_next_reload(_build_balance_with_version(7))

        await use_case.execute(actor_tg_id=42)

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BALANCE_RELOAD
        assert entry.actor_id == admin.id
        assert entry.target_kind == "balance"
        assert entry.target_id == "balance.yaml"
        assert entry.before == {"version": 1}
        assert entry.after == {"version": 7}
        assert entry.reason == "admin_balance_reload"
        assert entry.idempotency_key is not None
        assert entry.idempotency_key.startswith("balance_reload:42:")
        assert entry.occurred_at == clock.now()
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_same_version_after_reload_is_valid(self) -> None:
        # Файл не меняли — reload прошёл, before == after.
        use_case, admins, _, audit, _, _, _ = _build(initial_version=3)
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        result = await use_case.execute(actor_tg_id=42)

        assert result.version_before == 3
        assert result.version_after == 3
        assert len(audit.entries) == 1

    async def test_invalid_yaml_propagates_config_error_no_audit(self) -> None:
        # Если reloader-у плохо — use-case не должен глушить ошибку и
        # не должен писать аудит (нет state change).
        uow = FakeUnitOfWork()
        audit = FakeAuditLogger()
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        balance = FakeBalanceConfig(_build_balance_with_version(1))

        broken_reloader = MagicMock(spec=IBalanceReloader)
        broken_reloader.reload.side_effect = ConfigError("yaml broken")

        use_case = ReloadBalance(
            uow=uow,
            admins=admins,
            balance=balance,
            reloader=broken_reloader,
            audit=audit,
            admin_audit=FakeAdminAuditLogger(),
            authz=RoleBasedAdminAuthorizationPolicy(),
            clock=FakeClock(datetime(2026, 5, 4, tzinfo=UTC)),
        )

        with pytest.raises(ConfigError):
            await use_case.execute(actor_tg_id=42)

        assert audit.entries == []
        assert uow.commits == 0
