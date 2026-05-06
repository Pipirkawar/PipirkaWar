"""Реализация `IDailyHeadRepository` поверх таблицы `daily_heads` (Спринт 2.3.B)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.daily_head import (
    DailyHeadAlreadyAssignedError,
    DailyHeadAssignment,
    DailyHeadSource,
    IDailyHeadRepository,
)
from pipirik_wars.infrastructure.db.models import DailyHeadAssignmentORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc


def _row_to_entity(row: DailyHeadAssignmentORM) -> DailyHeadAssignment:
    """Маппит ORM-строку в доменный VO с tzinfo-восстановлением для SQLite."""
    return DailyHeadAssignment(
        id=row.id,
        clan_id=row.clan_id,
        player_id=row.player_id,
        moscow_date=row.moscow_date,
        source=DailyHeadSource(row.source),
        bonus_cm=row.bonus_cm,
        assigned_at=ensure_utc(row.assigned_at),
    )


class SqlAlchemyDailyHeadRepository(IDailyHeadRepository):
    """Persistence-реализация `IDailyHeadRepository` через UoW.

    Идемпотентность гонки кнопка-vs-cron гарантирует UNIQUE-индекс
    ``(clan_id, moscow_date)``. Доменный сервис сначала проверяет
    существование, но если две конкурентные транзакции прошли проверку
    одновременно — БД отбросит дубль `IntegrityError`-ом, а репозиторий
    конвертирует его в `DailyHeadAlreadyAssignedError`. Use-case 2.3.C
    перехватит ошибку и сделает повторный `get_by_clan_and_date(...)`,
    чтобы вернуть запись от победившего агента.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_by_clan_and_date(
        self,
        *,
        clan_id: int,
        moscow_date: date,
    ) -> DailyHeadAssignment | None:
        result = await self._uow.session.execute(
            select(DailyHeadAssignmentORM).where(
                DailyHeadAssignmentORM.clan_id == clan_id,
                DailyHeadAssignmentORM.moscow_date == moscow_date,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)

    async def add(self, assignment: DailyHeadAssignment) -> DailyHeadAssignment:
        row = DailyHeadAssignmentORM(
            clan_id=assignment.clan_id,
            player_id=assignment.player_id,
            moscow_date=assignment.moscow_date,
            source=assignment.source.value,
            bonus_cm=assignment.bonus_cm,
            assigned_at=assignment.assigned_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DailyHeadAlreadyAssignedError(
                clan_id=assignment.clan_id,
                moscow_date=assignment.moscow_date,
            ) from exc
        return _row_to_entity(row)

    async def list_recent_for_clan(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[DailyHeadAssignment]:
        if limit <= 0:
            return ()
        result = await self._uow.session.execute(
            select(DailyHeadAssignmentORM)
            .where(DailyHeadAssignmentORM.clan_id == clan_id)
            .order_by(
                DailyHeadAssignmentORM.assigned_at.desc(),
                DailyHeadAssignmentORM.id.desc(),
            )
            .limit(limit),
        )
        rows = result.scalars().all()
        return tuple(_row_to_entity(row) for row in rows)
