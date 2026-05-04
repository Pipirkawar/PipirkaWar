"""Реализация `ISignupQueueRepository` поверх таблицы `signup_queue`."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
    SignupQueueEntry,
)
from pipirik_wars.infrastructure.db.models import SignupQueueORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc


def _row_to_entity(row: SignupQueueORM, *, position: int) -> SignupQueueEntry:
    return SignupQueueEntry(
        id=row.id,
        tg_id=row.tg_id,
        username=row.username,
        locale=row.locale,
        position=position,
        enqueued_at=ensure_utc(row.enqueued_at),
    )


class SqlAlchemySignupQueueRepository(ISignupQueueRepository):
    """`tg_id` — UNIQUE; повторный INSERT падает на `IntegrityError`
    и преобразуется в `AlreadyQueuedError`. Все методы исполняются
    внутри активного `SqlAlchemyUnitOfWork`.

    `position` считается «на лету» — `1 + кол-во записей старше нашей`,
    одинаковое значение для одного и того же `tg_id` сохраняется,
    пока кто-то впереди не уйдёт `pop_front`-ом.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def enqueue(self, *, entry: SignupQueueEntry) -> SignupQueueEntry:
        if entry.id is not None:
            msg = f"SignupQueueEntry with pre-set id={entry.id} cannot be enqueued"
            raise ValueError(msg)
        row = SignupQueueORM(
            tg_id=entry.tg_id,
            username=entry.username,
            locale=entry.locale,
            enqueued_at=entry.enqueued_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            raise AlreadyQueuedError(tg_id=entry.tg_id) from exc
        position = await self._position_of(row.tg_id, row.enqueued_at)
        return _row_to_entity(row, position=position)

    async def get_by_tg_id(self, tg_id: int) -> SignupQueueEntry | None:
        result = await self._uow.session.execute(
            select(SignupQueueORM).where(SignupQueueORM.tg_id == tg_id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        position = await self._position_of(row.tg_id, row.enqueued_at)
        return _row_to_entity(row, position=position)

    async def size(self) -> int:
        result = await self._uow.session.execute(
            select(func.count()).select_from(SignupQueueORM),
        )
        return int(result.scalar_one())

    async def pop_front(self, *, limit: int) -> list[SignupQueueEntry]:
        if limit <= 0:
            return []
        result = await self._uow.session.execute(
            select(SignupQueueORM)
            .order_by(SignupQueueORM.enqueued_at.asc(), SignupQueueORM.id.asc())
            .limit(limit),
        )
        rows = list(result.scalars().all())
        if not rows:
            return []
        entries = [_row_to_entity(row, position=index + 1) for index, row in enumerate(rows)]
        ids_to_delete = [row.id for row in rows]
        await self._uow.session.execute(
            delete(SignupQueueORM).where(SignupQueueORM.id.in_(ids_to_delete)),
        )
        return entries

    async def _position_of(self, tg_id: int, enqueued_at: object) -> int:
        result = await self._uow.session.execute(
            select(func.count()).where(
                SignupQueueORM.enqueued_at < enqueued_at,
            ),
        )
        ahead = int(result.scalar_one())
        # Защита от ничьих по `enqueued_at`: добиваем сравнением по `tg_id`,
        # чтобы не получить «два первых места».
        result_ties = await self._uow.session.execute(
            select(func.count()).where(
                SignupQueueORM.enqueued_at == enqueued_at,
                SignupQueueORM.tg_id < tg_id,
            ),
        )
        ahead += int(result_ties.scalar_one())
        return ahead + 1
