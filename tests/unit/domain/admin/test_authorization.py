"""Unit-тесты RBAC-политики (Спринт 2.5-D.8 + D.11, ГДД §18.6.2).

D.11 — выровненная coverage: каждая команда из `AdminCommandKind`
проверяется против каждой роли из `AdminRole` (полная матрица
22 × 4 = 88 кейсов через `itertools.product`). Кейсы генерируются
из независимо заданной группировки команд по уровням доступа
(`_EXPECTED_ALLOWED_ROLES` ниже) — если в политике появится дрейф от
ГДД, тесты упадут до ревью.
Также: инвариант fail-closed для inactive-админа проверяется
для каждой роли (не только SUPER_ADMIN).
"""

from __future__ import annotations

import itertools
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


# ── Authoritative expected matrix (D.11) ────────────────────────────────
# Группы команд из ГДД §18.6.2; роли, которым группа разрешена,
# перечислены в `_build_expected_matrix()`. Из этого собирается
# полная таблица `(command_kind) → frozenset[AdminRole]`. Тесты сверяют
# реализацию политики против этой таблицы независимо от того, как
# реализована матрица в `RoleBasedAdminAuthorizationPolicy._matrix`.
_READ_SIDE_COMMANDS: frozenset[AdminCommandKind] = frozenset(
    {
        AdminCommandKind.FIND_PLAYER,
        AdminCommandKind.GET_PLAYER_CARD,
        AdminCommandKind.GET_CLAN_CARD,
        AdminCommandKind.GET_CLAN_DAILY_HEAD_HISTORY,
        AdminCommandKind.GET_BALANCE_VALUE,
        AdminCommandKind.GET_ADMIN_AUDIT_TRAIL,
        AdminCommandKind.ADMIN_STATS,
    },
)
_CONFIRM_FLOW_COMMANDS: frozenset[AdminCommandKind] = frozenset(
    {
        AdminCommandKind.REQUEST_ADMIN_CONFIRM,
        AdminCommandKind.VERIFY_ADMIN_CONFIRM,
    },
)
_SUPPORT_OPS_COMMANDS: frozenset[AdminCommandKind] = frozenset(
    {
        AdminCommandKind.FREEZE_PLAYER,
        AdminCommandKind.UNFREEZE_PLAYER,
        AdminCommandKind.BAN_PLAYER,
        AdminCommandKind.FREEZE_CLAN,
        AdminCommandKind.UNFREEZE_CLAN,
    },
)
_ECONOMY_COMMANDS: frozenset[AdminCommandKind] = frozenset(
    {
        AdminCommandKind.GRANT_LENGTH,
        AdminCommandKind.GRANT_THICKNESS,
        AdminCommandKind.SET_BALANCE_VALUE,
        AdminCommandKind.RELOAD_BALANCE,
    },
)
_SUPER_ONLY_COMMANDS: frozenset[AdminCommandKind] = frozenset(
    {
        AdminCommandKind.LIFT_ANTICHEAT_BAN,
        AdminCommandKind.SET_MAX_DAU,
        AdminCommandKind.BROADCAST_ANNOUNCEMENT,
        AdminCommandKind.SETUP_TOTP,
    },
)


def _build_expected_matrix() -> dict[AdminCommandKind, frozenset[AdminRole]]:
    matrix: dict[AdminCommandKind, frozenset[AdminRole]] = {}
    for command in _READ_SIDE_COMMANDS:
        matrix[command] = frozenset(AdminRole)
    for command in _CONFIRM_FLOW_COMMANDS:
        matrix[command] = frozenset(
            {AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST, AdminRole.SUPPORT},
        )
    for command in _SUPPORT_OPS_COMMANDS:
        matrix[command] = frozenset({AdminRole.SUPER_ADMIN, AdminRole.SUPPORT})
    for command in _ECONOMY_COMMANDS:
        matrix[command] = frozenset({AdminRole.SUPER_ADMIN, AdminRole.ECONOMIST})
    for command in _SUPER_ONLY_COMMANDS:
        matrix[command] = frozenset({AdminRole.SUPER_ADMIN})
    return matrix


_EXPECTED_ALLOWED_ROLES: dict[AdminCommandKind, frozenset[AdminRole]] = _build_expected_matrix()


_FULL_MATRIX_CASES: list[tuple[AdminRole, AdminCommandKind, bool]] = [
    (role, command, role in _EXPECTED_ALLOWED_ROLES[command])
    for role, command in itertools.product(AdminRole, AdminCommandKind)
]


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


class TestRoleCommandMatrixExhaustive:
    """Полная матрица `AdminRole × AdminCommandKind` (D.11).

    Любая новая команда / роль автоматически расширяет это покрытие
    (через `itertools.product` + `_EXPECTED_ALLOWED_ROLES`); если в
    политике добавится команда без правила или у группы изменится
    политика без правки этих тестов — упадём с понятным дифом.
    """

    def test_consistency_every_command_kind_has_expected_rule(self) -> None:
        """Все значения `AdminCommandKind` покрыты ожиданиями.

        Защищает от ситуации «добавили команду в enum, но не в
        тесты» — иначе exhaustive-матрица «по тихому» пропустит её.
        """
        assert set(_EXPECTED_ALLOWED_ROLES) == set(AdminCommandKind)

    @pytest.mark.parametrize(
        ("role", "command", "expected"),
        _FULL_MATRIX_CASES,
        ids=[
            f"{role.value}-{command.value}-{'allow' if expected else 'deny'}"
            for role, command, expected in _FULL_MATRIX_CASES
        ],
    )
    def test_full_matrix_active_admin(
        self,
        *,
        role: AdminRole,
        command: AdminCommandKind,
        expected: bool,
    ) -> None:
        policy = RoleBasedAdminAuthorizationPolicy()
        assert policy.is_authorized(_admin(role), command) is expected

    @pytest.mark.parametrize("role", list(AdminRole), ids=lambda r: r.value)
    def test_inactive_admin_denied_for_every_role(
        self,
        *,
        role: AdminRole,
    ) -> None:
        """Inactive-админ всегда отказан, даже если роль покрывает команду.

        Last-line-of-defense: use-case по контракту проверяет
        `is_active` до вызова policy, но политика обязана
        возвращать `False` сама. Проверяем для команды, которая в
        активном состоянии для этой роли разрешена (read-side есть
        у всех ролей).
        """
        policy = RoleBasedAdminAuthorizationPolicy()
        admin = _admin(role, is_active=False)
        assert not policy.is_authorized(admin, AdminCommandKind.FIND_PLAYER)


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
