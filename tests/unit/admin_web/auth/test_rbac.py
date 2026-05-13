"""Unit-тесты RBAC enforcement для admin-web (Sprint 4.5-B, task 4.5.2).

Тестирует ``require_permission`` — dependency-factory, возвращающую
async-callable, который проверяет:
- наличие сессии + TOTP (делегирует ``require_totp_verified``);
- загрузку Admin из БД;
- RBAC-проверку через ``IAdminAuthorizationPolicy``;
- запись ``ADMIN_AUTHORIZATION_DENIED`` в audit при отказе;
- HTTP 403 при отсутствии прав.
"""

from __future__ import annotations

from pipirik_wars.admin_web.auth.rbac import require_permission
from pipirik_wars.domain.admin.authorization import (
    AdminCommandKind,
    IAdminAuthorizationPolicy,
    RoleBasedAdminAuthorizationPolicy,
)
from pipirik_wars.domain.admin.entities import Admin, AdminRole


class TestRequirePermissionFactory:
    """Test that require_permission returns a callable for each command kind."""

    def test_returns_callable(self) -> None:
        dep = require_permission(AdminCommandKind.ADMIN_STATS)
        assert callable(dep)

    def test_different_commands_return_different_callables(self) -> None:
        dep_a = require_permission(AdminCommandKind.ADMIN_STATS)
        dep_b = require_permission(AdminCommandKind.BAN_PLAYER)
        assert dep_a is not dep_b

    def test_every_command_kind_produces_callable(self) -> None:
        for kind in AdminCommandKind:
            dep = require_permission(kind)
            assert callable(dep), f"require_permission({kind}) must return callable"


class TestRBACPolicyMatrix:
    """Verify the RBAC matrix covers all roles and permissions correctly.

    These are pure-domain unit tests on the policy object — no I/O.
    """

    def setup_method(self) -> None:
        self.policy: IAdminAuthorizationPolicy = RoleBasedAdminAuthorizationPolicy()

    def _admin(self, role: AdminRole, *, active: bool = True) -> Admin:
        from datetime import UTC, datetime  # noqa: PLC0415

        return Admin(
            id=1,
            tg_id=100,
            role=role,
            is_active=active,
            created_at=datetime.now(tz=UTC),
            totp_secret="JBSWY3DPEHPK3PXP",
        )

    # ── READ-SIDE: all active admins can access ──

    def test_read_only_can_find_player(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.FIND_PLAYER) is True

    def test_read_only_can_get_player_card(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_PLAYER_CARD) is True

    def test_read_only_can_get_clan_card(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_CLAN_CARD) is True

    def test_read_only_can_get_balance_value(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_BALANCE_VALUE) is True

    def test_read_only_can_admin_stats(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.ADMIN_STATS) is True

    def test_read_only_can_get_audit_trail(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_ADMIN_AUDIT_TRAIL) is True

    def test_read_only_can_get_clan_daily_head_history(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert (
            self.policy.is_authorized(admin, AdminCommandKind.GET_CLAN_DAILY_HEAD_HISTORY) is True
        )

    # ── READ-ONLY cannot do mutations ──

    def test_read_only_cannot_freeze_player(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PLAYER) is False

    def test_read_only_cannot_ban_player(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.BAN_PLAYER) is False

    def test_read_only_cannot_grant_length(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.GRANT_LENGTH) is False

    def test_read_only_cannot_set_balance(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.SET_BALANCE_VALUE) is False

    def test_read_only_cannot_broadcast(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.BROADCAST_ANNOUNCEMENT) is False

    # ── SUPPORT: can do support ops, cannot do economy / super-admin ──

    def test_support_can_freeze_player(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PLAYER) is True

    def test_support_can_unfreeze_player(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.UNFREEZE_PLAYER) is True

    def test_support_can_ban_player(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.BAN_PLAYER) is True

    def test_support_can_freeze_clan(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_CLAN) is True

    def test_support_can_unfreeze_clan(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.UNFREEZE_CLAN) is True

    def test_support_cannot_grant_length(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.GRANT_LENGTH) is False

    def test_support_cannot_set_balance(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.SET_BALANCE_VALUE) is False

    def test_support_cannot_broadcast(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.BROADCAST_ANNOUNCEMENT) is False

    def test_support_cannot_lift_anticheat_ban(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.LIFT_ANTICHEAT_BAN) is False

    # ── ECONOMIST: can do economy, cannot do support / super-admin ──

    def test_economist_can_grant_length(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.GRANT_LENGTH) is True

    def test_economist_can_grant_thickness(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.GRANT_THICKNESS) is True

    def test_economist_can_set_balance(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.SET_BALANCE_VALUE) is True

    def test_economist_can_reload_balance(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.RELOAD_BALANCE) is True

    def test_economist_cannot_freeze_player(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PLAYER) is False

    def test_economist_cannot_ban_player(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.BAN_PLAYER) is False

    def test_economist_cannot_broadcast(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.BROADCAST_ANNOUNCEMENT) is False

    # ── SUPER_ADMIN: can do everything ──

    def test_super_admin_can_find_player(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.FIND_PLAYER) is True

    def test_super_admin_can_freeze_player(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PLAYER) is True

    def test_super_admin_can_grant_length(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.GRANT_LENGTH) is True

    def test_super_admin_can_broadcast(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.BROADCAST_ANNOUNCEMENT) is True

    def test_super_admin_can_lift_anticheat_ban(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.LIFT_ANTICHEAT_BAN) is True

    def test_super_admin_can_setup_totp(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.SETUP_TOTP) is True

    def test_super_admin_can_set_max_dau(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.SET_MAX_DAU) is True

    # ── Inactive admin denied for every command ──

    def test_inactive_super_admin_denied(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN, active=False)
        for kind in AdminCommandKind:
            assert self.policy.is_authorized(admin, kind) is False, (
                f"Inactive admin must be denied: {kind}"
            )

    def test_inactive_read_only_denied(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY, active=False)
        assert self.policy.is_authorized(admin, AdminCommandKind.FIND_PLAYER) is False

    # ── Confirm-flow: available to SUPPORT+, not READ_ONLY ──

    def test_read_only_cannot_request_confirm(self) -> None:
        admin = self._admin(AdminRole.READ_ONLY)
        assert self.policy.is_authorized(admin, AdminCommandKind.REQUEST_ADMIN_CONFIRM) is False

    def test_support_can_request_confirm(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.REQUEST_ADMIN_CONFIRM) is True

    def test_economist_can_request_confirm(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.REQUEST_ADMIN_CONFIRM) is True

    # ── Prize-pool commands: super-admin only ──

    def test_support_cannot_get_prize_pool(self) -> None:
        admin = self._admin(AdminRole.SUPPORT)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_PRIZE_POOL) is False

    def test_super_admin_can_get_prize_pool(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.GET_PRIZE_POOL) is True

    def test_super_admin_can_freeze_payouts(self) -> None:
        admin = self._admin(AdminRole.SUPER_ADMIN)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PAYOUTS) is True

    def test_economist_cannot_freeze_payouts(self) -> None:
        admin = self._admin(AdminRole.ECONOMIST)
        assert self.policy.is_authorized(admin, AdminCommandKind.FREEZE_PAYOUTS) is False
