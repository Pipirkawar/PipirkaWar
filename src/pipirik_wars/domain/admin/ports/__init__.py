"""Доменные порты подсистемы админ-доступа.

`IAdminAuditLogger` (Спринт 2.5-A.1) — отдельный аудит-лог админских
мутаций (таблица `admin_audit_log`, ГДД §18.6). От общего `audit_log`
отличается тем, что:

- содержит обязательное поле `admin_id` (FK → `admins.id`) — все записи
  привязаны к конкретному админу;
- хранит контекст команды (`tg_chat_id`, `ip`, `source`) для будущей
  команды `/audit <admin>`;
- источник ограничен whitelist-ом `bot` / `web` (без органических
  источников вроде `forest` / `oracle`).

`IAdminConfirmStore` + `ITotpVerifier` (Спринт 2.5-A.3) — однократный
TTL-store ожидающих подтверждений + обёртка над `pyotp` для проверки
6-значных кодов.
"""

from pipirik_wars.domain.admin.ports.admin_audit import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditRecord,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminAuditQuery,
)
from pipirik_wars.domain.admin.ports.admin_confirm import (
    IAdminConfirmStore,
    ITotpVerifier,
)

__all__ = [
    "AdminAuditAction",
    "AdminAuditEntry",
    "AdminAuditRecord",
    "AdminAuditSource",
    "IAdminAuditLogger",
    "IAdminAuditQuery",
    "IAdminConfirmStore",
    "ITotpVerifier",
]
