"""Unit-тесты RBAC-политики (Спринт 2.5-D.8, ГДД §18.6.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.admin import (
    Admin,
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    AdminRole,
    RoleBasedAdminAuthorizationPolicy,
)

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _admin(role: AdminRole, *, is_active: bool = True) -> Admin:
    return Admin(
        id=1,
        tg_id=42,
        role=role,
        is_active=is_active,
        created_at=_NOW,
        created_by_admin_id=None,
        note=None,
        totp_secret=None,
    )


class TestRoleBasedAdminAuthorizationPolicy:
    def test_super_admin_allows_all_known_commands(self) -> None:
        policy = RoleBasedAdminAuthorizationPolicy()
        admin = _admin(AdminRole.SUPER_ADMIN)
        for command in AdminCommandKind:
            assert policy.is_authorized(admin, command), f"super_admin must be allowed to {command}"

    def test_inactive_admin_denied_even_if_role_matches(self) -> None:
        policy = RoleBasedAdminAuthorizationPolicy()
        admin = _admin(AdminRole.SUPER_ADMIN, is_active=False)
        assert not policy.is_authorized(admin, AdminCommandKind.BAN_PLAYER)

    @pytest.mark.parametrize(
        ("role", "command", "expected"),
        [
            # Read-only — все доступно.
            (AdminRole.READ_ONLY, AdminCommandKind.FIND_PLAYER, True),
            (AdminRole.READ_ONLY, AdminCommandKind.GET_PLAYER_CARD, True),
            (AdminRole.READ_ONLY, AdminCommandKind.GET_BALANCE_VALUE, True),
            (AdminRole.READ_ONLY, AdminCommandKind.GET_ADMIN_AUDIT_TRAIL, True),
            # Read-only НЕ может мутировать.
            (AdminRole.READ_ONLY, AdminCommandKind.BAN_PLAYER, False),
            (AdminRole.READ_ONLY, AdminCommandKind.FREEZE_CLAN, False),
            (AdminRole.READ_ONLY, AdminCommandKind.GRANT_LENGTH, False),
            (AdminRole.READ_ONLY, AdminCommandKind.SET_BALANCE_VALUE, False),
            (AdminRole.READ_ONLY, AdminCommandKind.LIFT_ANTICHEAT_BAN, False),
            (AdminRole.READ_ONLY, AdminCommandKind.REQUEST_ADMIN_CONFIRM, False),
            # Support — операционка над игроками/кланами.
            (AdminRole.SUPPORT, AdminCommandKind.FREEZE_PLAYER, True),
            (AdminRole.SUPPORT, AdminCommandKind.UNFREEZE_PLAYER, True),
            (AdminRole.SUPPORT, AdminCommandKind.BAN_PLAYER, True),
            (AdminRole.SUPPORT, AdminCommandKind.FREEZE_CLAN, True),
            (AdminRole.SUPPORT, AdminCommandKind.UNFREEZE_CLAN, True),
            (AdminRole.SUPPORT, AdminCommandKind.REQUEST_ADMIN_CONFIRM, True),
            (AdminRole.SUPPORT, AdminCommandKind.VERIFY_ADMIN_CONFIRM, True),
            # Support НЕ может править экономику.
            (AdminRole.SUPPORT, AdminCommandKind.GRANT_LENGTH, False),
            (AdminRole.SUPPORT, AdminCommandKind.GRANT_THICKNESS, False),
            (AdminRole.SUPPORT, AdminCommandKind.SET_BALANCE_VALUE, False),
            (AdminRole.SUPPORT, AdminCommandKind.RELOAD_BALANCE, False),
            # Support НЕ может в super-admin-команды.
            (AdminRole.SUPPORT, AdminCommandKind.LIFT_ANTICHEAT_BAN, False),
            (AdminRole.SUPPORT, AdminCommandKind.SETUP_TOTP, False),
            (AdminRole.SUPPORT, AdminCommandKind.BROADCAST_ANNOUNCEMENT, False),
            # Economist — экономика + read-side.
            (AdminRole.ECONOMIST, AdminCommandKind.GRANT_LENGTH, True),
            (AdminRole.ECONOMIST, AdminCommandKind.GRANT_THICKNESS, True),
            (AdminRole.ECONOMIST, AdminCommandKind.SET_BALANCE_VALUE, True),
            (AdminRole.ECONOMIST, AdminCommandKind.RELOAD_BALANCE, True),
            (AdminRole.ECONOMIST, AdminCommandKind.GET_BALANCE_VALUE, True),
            (AdminRole.ECONOMIST, AdminCommandKind.REQUEST_ADMIN_CONFIRM, True),
            # Economist НЕ может банить/морозить.
            (AdminRole.ECONOMIST, AdminCommandKind.BAN_PLAYER, False),
            (AdminRole.ECONOMIST, AdminCommandKind.FREEZE_PLAYER, False),
            (AdminRole.ECONOMIST, AdminCommandKind.FREEZE_CLAN, False),
            # Economist НЕ может в super-admin-команды.
            (AdminRole.ECONOMIST, AdminCommandKind.LIFT_ANTICHEAT_BAN, False),
            (AdminRole.ECONOMIST, AdminCommandKind.SETUP_TOTP, False),
        ],
    )
    def test_matrix(
        self,
        *,
        role: AdminRole,
        command: AdminCommandKind,
        expected: bool,
    ) -> None:
        policy = RoleBasedAdminAuthorizationPolicy()
        assert policy.is_authorized(_admin(role), command) is expected


class TestAdminAuthorizationDeniedError:
    def test_carries_command_role_and_detail(self) -> None:
        err = AdminAuthorizationDeniedError(
            command_kind=AdminCommandKind.BAN_PLAYER,
            actor_role=AdminRole.READ_ONLY,
            detail="role=read_only command=ban_player target='12345'",
        )
        assert err.command_kind is AdminCommandKind.BAN_PLAYER
        assert err.actor_role is AdminRole.READ_ONLY
        assert "ban_player" in str(err)
        assert "read_only" in str(err)
