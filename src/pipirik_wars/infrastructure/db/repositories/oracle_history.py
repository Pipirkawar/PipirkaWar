"""Реализация `IOracleHistoryRepository` поверх таблицы `oracle_invocations`."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.oracle import IOracleHistoryRepository, OracleInvocation
from pipirik_wars.infrastructure.db.models import OracleInvocationORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _row_to_entity(row: OracleInvocationORM) -> OracleInvocation:
    return OracleInvocation(
        player_id=row.player_id,
        moscow_date=row.moscow_date,
        bonus_cm=row.bonus_cm,
        template_id=row.template_id,
        occurred_at=ensure_utc(row.occurred_at),
    )


class SqlAlchemyOracleHistoryRepository(IOracleHistoryRepository):
    """`(player_id, moscow_date)` — UNIQUE-индекс.

    Повторный INSERT на тот же ключ падает БД-уровневым `IntegrityError`,
    репозиторий преобразует его в доменный `IntegrityError`. Use-case
    `InvokeOracle` это перехватывает и трактует как
    `OracleAlreadyUsedTodayError`.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, invocation: OracleInvocation) -> None:
        row = OracleInvocationORM(
            player_id=invocation.player_id,
            moscow_date=invocation.moscow_date,
            bonus_cm=invocation.bonus_cm,
            template_id=invocation.template_id,
            occurred_at=invocation.occurred_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add oracle_invocation for player_id={invocation.player_id} "
                f"on {invocation.moscow_date.isoformat()}: {exc.orig}"
            ) from exc

    async def get_for_day(
        self,
        *,
        player_id: int,
        moscow_date: date,
    ) -> OracleInvocation | None:
        result = await self._uow.session.execute(
            select(OracleInvocationORM).where(
                OracleInvocationORM.player_id == player_id,
                OracleInvocationORM.moscow_date == moscow_date,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)
