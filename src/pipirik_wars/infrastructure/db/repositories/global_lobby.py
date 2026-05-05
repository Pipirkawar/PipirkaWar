"""Реализация `IGlobalLobbyRepository` поверх таблицы `pvp_global_lobby` (Спринт 2.1.F).

FIFO-очередь pending PvP-вызовов в режиме ``GLOBAL_ONLY``. Связь 1:1 с
``pvp_duels`` через PK = ``duel_id`` (CASCADE).

Потокобезопасность `pop_oldest`:

* На PostgreSQL — ``SELECT … FOR UPDATE SKIP LOCKED`` (несколько
  параллельных воркеров не «выхватят» одну и ту же запись).
* На SQLite (тесты) — ``FOR UPDATE`` не поддерживается; полагаемся на
  сериализацию через UoW-транзакцию.

Идемпотентность `enqueue`:

* На PostgreSQL — ``INSERT … ON CONFLICT DO NOTHING``.
* На SQLite — ``INSERT OR IGNORE`` через ``sqlite_insert.on_conflict_do_nothing``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import Insert as PgInsert, insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert, insert as sqlite_insert
from sqlalchemy.sql.dml import Insert as DialectInsert

from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository, LobbyEntry
from pipirik_wars.infrastructure.db.models import PvpGlobalLobbyORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc


class SqlAlchemyGlobalLobbyRepository(IGlobalLobbyRepository):
    """SQL-реализация FIFO-лобби PvP."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def enqueue(self, *, duel_id: int, enqueued_at: datetime) -> bool:
        session = self._uow.session
        values = {"duel_id": duel_id, "enqueued_at": enqueued_at}
        dialect = session.bind.dialect.name if session.bind is not None else ""
        stmt: DialectInsert
        if dialect == "postgresql":
            pg_stmt: PgInsert = pg_insert(PvpGlobalLobbyORM).values(values)
            stmt = pg_stmt.on_conflict_do_nothing(index_elements=[PvpGlobalLobbyORM.duel_id])
        else:
            sl_stmt: SqliteInsert = sqlite_insert(PvpGlobalLobbyORM).values(values)
            stmt = sl_stmt.on_conflict_do_nothing(index_elements=[PvpGlobalLobbyORM.duel_id])
        result = await session.execute(stmt)
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("INSERT must return CursorResult")
        return bool(result.rowcount and result.rowcount > 0)

    async def pop_oldest(self) -> LobbyEntry | None:
        session = self._uow.session
        dialect = session.bind.dialect.name if session.bind is not None else ""
        stmt = select(PvpGlobalLobbyORM).order_by(PvpGlobalLobbyORM.enqueued_at.asc()).limit(1)
        if dialect == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        await session.execute(
            delete(PvpGlobalLobbyORM).where(PvpGlobalLobbyORM.duel_id == row.duel_id),
        )
        return LobbyEntry(duel_id=row.duel_id, enqueued_at=ensure_utc(row.enqueued_at))

    async def remove(self, *, duel_id: int) -> bool:
        result = await self._uow.session.execute(
            delete(PvpGlobalLobbyORM).where(PvpGlobalLobbyORM.duel_id == duel_id),
        )
        if not isinstance(result, CursorResult):  # pragma: no cover
            raise RuntimeError("DELETE must return CursorResult")
        return bool(result.rowcount and result.rowcount > 0)

    async def is_in_lobby(self, *, duel_id: int) -> bool:
        result = await self._uow.session.execute(
            select(PvpGlobalLobbyORM.duel_id).where(PvpGlobalLobbyORM.duel_id == duel_id),
        )
        return result.scalar_one_or_none() is not None
