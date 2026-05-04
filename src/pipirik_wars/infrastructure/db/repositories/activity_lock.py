"""Реализация `IActivityLockRepository` поверх таблицы `activity_locks`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import Insert as PgInsert, insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert, insert as sqlite_insert
from sqlalchemy.sql.dml import Insert as DialectInsert

from pipirik_wars.domain.security import (
    ActivityLock,
    IActivityLockRepository,
    LockReason,
)
from pipirik_wars.infrastructure.db.models import ActivityLockORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyActivityLockRepository(IActivityLockRepository):
    """`(actor_kind, actor_id)` — PK; повторный INSERT на существующем
    активном блоке падает на `ON CONFLICT`. Если же существующий блок
    уже истёк — апдейтим его in-place (то есть «перезахватываем»).
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def try_acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        session = self._uow.session
        # 1. Чистим истёкшие чужие блоки этого актора (если есть).
        await session.execute(
            delete(ActivityLockORM).where(
                ActivityLockORM.actor_kind == actor_kind,
                ActivityLockORM.actor_id == actor_id,
                ActivityLockORM.expires_at <= now,
            ),
        )
        # 2. INSERT ... ON CONFLICT DO NOTHING.
        values = {
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "reason": reason.value,
            "acquired_at": now,
            "expires_at": expires_at,
        }
        dialect = session.bind.dialect.name if session.bind is not None else ""
        stmt: DialectInsert
        if dialect == "postgresql":
            pg_stmt: PgInsert = pg_insert(ActivityLockORM).values(values)
            stmt = pg_stmt.on_conflict_do_nothing(
                index_elements=[
                    ActivityLockORM.actor_kind,
                    ActivityLockORM.actor_id,
                ],
            )
        else:
            sl_stmt: SqliteInsert = sqlite_insert(ActivityLockORM).values(values)
            stmt = sl_stmt.on_conflict_do_nothing(
                index_elements=[
                    ActivityLockORM.actor_kind,
                    ActivityLockORM.actor_id,
                ],
            )
        result = await session.execute(stmt)
        # `rowcount` == 1, если запись действительно вставлена; 0 — если CONFLICT.
        # `Result` в общем случае не имеет rowcount, но INSERT возвращает CursorResult.
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("INSERT must return CursorResult")
        return bool(result.rowcount and result.rowcount > 0)

    async def release(self, *, actor_kind: str, actor_id: int) -> None:
        await self._uow.session.execute(
            delete(ActivityLockORM).where(
                ActivityLockORM.actor_kind == actor_kind,
                ActivityLockORM.actor_id == actor_id,
            ),
        )

    async def get(
        self,
        *,
        actor_kind: str,
        actor_id: int,
    ) -> ActivityLock | None:
        result = await self._uow.session.execute(
            select(ActivityLockORM).where(
                ActivityLockORM.actor_kind == actor_kind,
                ActivityLockORM.actor_id == actor_id,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ActivityLock(
            actor_kind=row.actor_kind,
            actor_id=row.actor_id,
            reason=LockReason(row.reason),
            acquired_at=row.acquired_at,
            expires_at=row.expires_at,
        )
