"""Read-side ``audit_log`` query (Sprint 4.5-F)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from pipirik_wars.domain.shared.ports.audit import AuditRecord, IAuditLogQuery
from pipirik_wars.infrastructure.db.models import AuditLogORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAuditLogQuery(IAuditLogQuery):
    """SQLAlchemy implementation of ``IAuditLogQuery``."""

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
        actor_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> Sequence[AuditRecord]:
        stmt = (
            select(AuditLogORM)
            .order_by(AuditLogORM.occurred_at.desc(), AuditLogORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if date_from is not None:
            stmt = stmt.where(AuditLogORM.occurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLogORM.occurred_at <= date_to)
        if actor_id is not None:
            stmt = stmt.where(AuditLogORM.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(AuditLogORM.action == action)
        if source is not None:
            stmt = stmt.where(AuditLogORM.source == source)

        rows = (await self._uow.session.execute(stmt)).scalars().all()
        return tuple(
            AuditRecord(
                id=r.id,
                occurred_at=r.occurred_at,
                action=r.action,
                actor_id=r.actor_id,
                target_kind=r.target_kind,
                target_id=r.target_id,
                reason=r.reason,
                source=r.source,
            )
            for r in rows
        )

    async def count(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        actor_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> int:
        stmt = select(func.count(AuditLogORM.id))
        if date_from is not None:
            stmt = stmt.where(AuditLogORM.occurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLogORM.occurred_at <= date_to)
        if actor_id is not None:
            stmt = stmt.where(AuditLogORM.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(AuditLogORM.action == action)
        if source is not None:
            stmt = stmt.where(AuditLogORM.source == source)

        result = await self._uow.session.execute(stmt)
        count_val: int = result.scalar_one()
        return count_val
