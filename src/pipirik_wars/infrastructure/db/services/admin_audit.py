"""Реализации портов поверх таблицы `admin_audit_log`.

`SqlAlchemyAdminAuditLogger` — write-side (`IAdminAuditLogger`).
`SqlAlchemyAdminAuditQuery` — read-side (`IAdminAuditQuery`,
Спринт 2.5-D.5: команда `/audit`).

Разделение по ISP: мутации зовут только `record(...)`, handler
`/audit` — только `list_recent(...)`. Обе реализации делят одну
таблицу и работают внутри одного контекста `IUnitOfWork`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditRecord,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminAuditQuery,
)
from pipirik_wars.infrastructure.db.models import AdminAuditLogORM, AdminORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAdminAuditLogger(IAdminAuditLogger):
    """Пишет admin-audit-запись в той же транзакции, что и сама мутация.

    Любая ошибка пробрасывается дальше — `IUnitOfWork.__aexit__` сделает
    rollback всей транзакции. ГДД §0: «без аудита операция не считается
    выполненной».
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def record(self, entry: AdminAuditEntry) -> None:
        row = AdminAuditLogORM(
            admin_id=entry.admin_id,
            action=entry.action.value,
            target_kind=entry.target_kind,
            target_id=entry.target_id,
            before=entry.before,
            after=entry.after,
            reason=entry.reason,
            idempotency_key=entry.idempotency_key,
            source=entry.source.value,
            tg_chat_id=entry.tg_chat_id,
            ip=entry.ip,
            occurred_at=entry.occurred_at,
        )
        self._uow.session.add(row)
        await self._uow.session.flush()


class SqlAlchemyAdminAuditQuery(IAdminAuditQuery):
    """Read-side `admin_audit_log` поверх SQLAlchemy (`/audit`).

    Один запрос с JOIN-ом к `admins` (чтобы вернуть `actor_tg_id`
    без N+1) под ix-индексами `ix_admin_audit_log_admin_id_occurred_at`
    и `ix_admin_audit_log_action`. Для запроса «всё подряд» (без
    фильтров) индексы не используются — но кардинальность таблицы
    в admin-сценарии маленькая, и сорт-merge по `occurred_at DESC`
    укладывается в TopN.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def list_recent(
        self,
        *,
        limit: int,
        target_admin_id: int | None = None,
        action: AdminAuditAction | None = None,
    ) -> Sequence[AdminAuditRecord]:
        stmt = (
            select(AdminAuditLogORM, AdminORM.tg_id)
            .join(AdminORM, AdminORM.id == AdminAuditLogORM.admin_id)
            .order_by(
                AdminAuditLogORM.occurred_at.desc(),
                AdminAuditLogORM.id.desc(),
            )
            .limit(limit)
        )
        if target_admin_id is not None:
            stmt = stmt.where(AdminAuditLogORM.admin_id == target_admin_id)
        if action is not None:
            stmt = stmt.where(AdminAuditLogORM.action == action.value)

        rows = (await self._uow.session.execute(stmt)).all()
        return tuple(
            AdminAuditRecord(
                id=log.id,
                actor_admin_id=log.admin_id,
                actor_tg_id=tg_id,
                action=AdminAuditAction(log.action),
                target_kind=log.target_kind,
                target_id=log.target_id,
                before=log.before,
                after=log.after,
                reason=log.reason,
                idempotency_key=log.idempotency_key,
                source=AdminAuditSource(log.source),
                tg_chat_id=log.tg_chat_id,
                ip=log.ip,
                occurred_at=log.occurred_at,
            )
            for log, tg_id in rows
        )
