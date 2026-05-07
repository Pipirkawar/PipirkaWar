"""Доменная подсистема админ-доступа.

`Admin` — это NOT игрок: это аккаунт с ролью (`super_admin`, `economist`,
`support`, `read_only`), идентифицируемый по `tg_id`. Используется и в
ТГ-админ-командах (`/admin_*`), и в опциональной веб-панели (Спринт 4.5).
ГДД §18.6, §18.6.4 (bootstrap).

В Спринте 2.5-A добавлены:

* порт `IAdminAuditLogger` + сущности `AdminAuditEntry` /
  `AdminAuditAction` / `AdminAuditSource` (таблица `admin_audit_log`,
  Спринт 2.5-A.1);
* VO `AdminConfirmRequest` / `AdminConfirmEntry` + ошибки и порты
  `IAdminConfirmStore` / `ITotpVerifier` (TOTP-подтверждение опасных
  команд, Спринт 2.5-A.3).
"""

from pipirik_wars.domain.admin.authorization import (
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    IAdminAuthorizationPolicy,
    RoleBasedAdminAuthorizationPolicy,
)
from pipirik_wars.domain.admin.confirm import (
    AdminConfirmEntry,
    AdminConfirmError,
    AdminConfirmRequest,
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    TotpNotConfiguredError,
)
from pipirik_wars.domain.admin.entities import Admin, AdminRole
from pipirik_wars.domain.admin.ports import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditRecord,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminAuditQuery,
    IAdminConfirmStore,
    ITotpVerifier,
)
from pipirik_wars.domain.admin.repositories import IAdminRepository

__all__ = [
    "Admin",
    "AdminAuditAction",
    "AdminAuditEntry",
    "AdminAuditRecord",
    "AdminAuditSource",
    "AdminAuthorizationDeniedError",
    "AdminCommandKind",
    "AdminConfirmEntry",
    "AdminConfirmError",
    "AdminConfirmRequest",
    "AdminRole",
    "ConfirmAdminMismatchError",
    "ConfirmCodeInvalidError",
    "ConfirmTokenExpiredError",
    "ConfirmTokenNotFoundError",
    "IAdminAuditLogger",
    "IAdminAuditQuery",
    "IAdminAuthorizationPolicy",
    "IAdminConfirmStore",
    "IAdminRepository",
    "ITotpVerifier",
    "RoleBasedAdminAuthorizationPolicy",
    "TotpNotConfiguredError",
]
