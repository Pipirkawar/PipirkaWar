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

Доп. порты появятся в 2.5-A.3 (`IAdminConfirmStore` для FSM TOTP).
"""

from pipirik_wars.domain.admin.ports.admin_audit import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    IAdminAuditLogger,
)

__all__ = [
    "AdminAuditAction",
    "AdminAuditEntry",
    "AdminAuditSource",
    "IAdminAuditLogger",
]
