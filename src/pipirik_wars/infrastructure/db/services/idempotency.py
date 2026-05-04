"""Реализация `IIdempotencyKey` поверх таблицы `idempotency_keys`."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert as PgInsert, insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert, insert as sqlite_insert
from sqlalchemy.sql.dml import Insert as DialectInsert

from pipirik_wars.domain.shared.ports import IIdempotencyKey
from pipirik_wars.infrastructure.db.models import IdempotencyKeyORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyIdempotencyService(IIdempotencyKey):
    """Идемпотентность через PK таблицы `idempotency_keys`.

    `mark` использует диалект-специфичный `INSERT ... ON CONFLICT DO NOTHING`
    (Postgres) или его эквивалент в SQLite. Это нужно потому, что
    `INSERT` без ON CONFLICT поднимает `IntegrityError` на дубликате,
    что портит транзакцию (требует rollback). Нам же нужно «уже было —
    ну и ладно».
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    def build(self, namespace: str, parts: Sequence[str]) -> str:
        if not namespace:
            raise ValueError("namespace must be non-empty")
        return namespace + ":" + "|".join(parts)

    async def is_seen(self, key: str) -> bool:
        result = await self._uow.session.execute(
            select(IdempotencyKeyORM.key).where(IdempotencyKeyORM.key == key),
        )
        return result.first() is not None

    async def mark(self, key: str, *, namespace: str) -> None:
        if not key.startswith(namespace + ":"):
            raise ValueError(
                f"key {key!r} does not match namespace {namespace!r}",
            )
        session = self._uow.session
        dialect = session.bind.dialect.name if session.bind is not None else ""
        values = {"key": key, "namespace": namespace}
        stmt: DialectInsert
        if dialect == "postgresql":
            pg_stmt: PgInsert = pg_insert(IdempotencyKeyORM).values(values)
            stmt = pg_stmt.on_conflict_do_nothing(
                index_elements=[IdempotencyKeyORM.key],
            )
        else:
            # SQLite (тесты) — синтаксис тот же, но через свой диалект.
            sl_stmt: SqliteInsert = sqlite_insert(IdempotencyKeyORM).values(values)
            stmt = sl_stmt.on_conflict_do_nothing(
                index_elements=[IdempotencyKeyORM.key],
            )
        await session.execute(stmt)
