"""Extended read-side ``admin_audit_log`` query (Sprint 4.5-F)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditRecord,
    AdminAuditSource,
    IAdminAuditWebQuery,
)
from pipirik_wars.infrastructure.db.models import AdminAuditLogORM, AdminORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAdminAuditWebQuery(IAdminAuditWebQuery):
    """SQLAlchemy implementation of ``IAdminAuditWebQuery``."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def list_records(
        self,
        *,
        limit: int,
        offset: int = 0,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> Sequence[AdminAuditRecord]:
        stmt = (
            select(AdminAuditLogORM, AdminORM.tg_id)
            .join(AdminORM, AdminORM.id == AdminAuditLogORM.admin_id)
            .order_by(
                AdminAuditLogORM.occurred_at.desc(),
                AdminAuditLogORM.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        if date_from is not None:
            stmt = stmt.where(AdminAuditLogORM.occurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AdminAuditLogORM.occurred_at <= date_to)
        if admin_id is not None:
            stmt = stmt.where(AdminAuditLogORM.admin_id == admin_id)
        if action is not None:
            stmt = stmt.where(AdminAuditLogORM.action == action)
        if source is not None:
            stmt = stmt.where(AdminAuditLogORM.source == source)

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

    async def count(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> int:
        stmt = select(func.count(AdminAuditLogORM.id))
        if date_from is not None:
            stmt = stmt.where(AdminAuditLogORM.occurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AdminAuditLogORM.occurred_at <= date_to)
        if admin_id is not None:
            stmt = stmt.where(AdminAuditLogORM.admin_id == admin_id)
        if action is not None:
            stmt = stmt.where(AdminAuditLogORM.action == action)
        if source is not None:
            stmt = stmt.where(AdminAuditLogORM.source == source)

        result = await self._uow.session.execute(stmt)
        count_val: int = result.scalar_one()
        return count_val
