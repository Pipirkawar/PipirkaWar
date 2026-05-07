"""Test-double-ы для `IAdminAuthorizationPolicy` (Спринт 2.5-D.8).

Чтобы не тащить в каждый unit-тест admin-use-case-а реальную матрицу
`RoleBasedAdminAuthorizationPolicy` и не зависеть от того, какие
команды разрешены конкретной роли, тесты используют:

* `FakeAdminAuthzAllowAll` — всегда разрешает (дефолт для
  «happy-path»-тестов use-case-а; они не проверяют RBAC, а
  фокусируются на бизнес-логике).
* `FakeAdminAuthzDenyAll` — всегда отказывает (для тестов на
  `ADMIN_AUTHORIZATION_DENIED` в admin-аудите и
  `AdminAuthorizationDeniedError`).
* `FakeAdminAuthzMatrix` — программируемая матрица, чтобы тесты
  моделировали «admin role=ECONOMIST дёргает GRANT_LENGTH (allow),
  но FREEZE_PLAYER (deny)».
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipirik_wars.domain.admin import (
    Admin,
    AdminCommandKind,
    IAdminAuthorizationPolicy,
)


@dataclass
class FakeAdminAuthzAllowAll(IAdminAuthorizationPolicy):
    """Всегда `True` (для happy-path-тестов use-case-а)."""

    def is_authorized(self, admin: Admin, command_kind: AdminCommandKind) -> bool:
        return admin.is_active


@dataclass
class FakeAdminAuthzDenyAll(IAdminAuthorizationPolicy):
    """Всегда `False` (для тестов на `ADMIN_AUTHORIZATION_DENIED`)."""

    def is_authorized(self, admin: Admin, command_kind: AdminCommandKind) -> bool:
        return False


@dataclass
class FakeAdminAuthzMatrix(IAdminAuthorizationPolicy):
    """Программируемая матрица. По умолчанию пустая → fail-closed.

    `allow[command_kind] = True/False`. Команда без явного правила
    отказывает (как и реальная политика).
    """

    allow: dict[AdminCommandKind, bool] = field(default_factory=dict)

    def is_authorized(self, admin: Admin, command_kind: AdminCommandKind) -> bool:
        if not admin.is_active:
            return False
        return self.allow.get(command_kind, False)


__all__ = [
    "FakeAdminAuthzAllowAll",
    "FakeAdminAuthzDenyAll",
    "FakeAdminAuthzMatrix",
]
