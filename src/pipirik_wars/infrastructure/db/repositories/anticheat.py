"""Реализация `IAnticheatRepository` поверх таблицы `audit_log` (Спринт 1.6.C).

Один SELECT-запрос с фильтром по `target_kind='player'` + `target_id` +
`source IN organic_sources` + `delta_cm > 0` + `occurred_at >= since`.
Composite-индекс `ix_audit_log_target_source_occurred` (миграция 0008)
покрывает первые три ключа; финальный фильтр по `delta_cm > 0` —
дешёвый bitmap-merge.

`COALESCE(SUM(...), 0)` обрабатывает кейс пустого результата (новый игрок
без organic-операций → 0 см).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select

from pipirik_wars.domain.anticheat import AnticheatWindow, IAnticheatRepository
from pipirik_wars.domain.shared.ports.audit import AuditSource
from pipirik_wars.infrastructure.db.models import AuditLogORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAnticheatRepository(IAnticheatRepository):
    """Аггрегатор `audit_log` под anti-cheat-окно."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def sum_organic_in_window(
        self,
        *,
        player_id: int,
        since: datetime,
        organic_sources: Iterable[AuditSource],
    ) -> AnticheatWindow:
        if player_id <= 0:
            raise ValueError(f"player_id must be > 0, got {player_id}")
        if since.tzinfo is None:
            raise ValueError(f"since must be timezone-aware (UTC), got naive {since!r}")

        # `tuple(...)` фиксирует итератор; пустой список → SQL `IN ()` невалиден,
        # поэтому возвращаем пустое окно без обращения к БД.
        sources = tuple(organic_sources)
        if not sources:
            return AnticheatWindow(player_id=player_id, since=since, organic_sum_cm=0)

        source_values = tuple(s.value for s in sources)

        stmt = select(func.coalesce(func.sum(AuditLogORM.delta_cm), 0)).where(
            AuditLogORM.target_kind == "player",
            AuditLogORM.target_id == str(player_id),
            AuditLogORM.source.in_(source_values),
            AuditLogORM.delta_cm.is_not(None),
            AuditLogORM.delta_cm > 0,
            AuditLogORM.occurred_at >= since,
        )

        result = await self._uow.session.execute(stmt)
        # COALESCE(SUM(...), 0) гарантирует не-None результат, но mypy без
        # рантайм-знания этого не выводит; явно подстраховываемся.
        raw = result.scalar_one()
        organic_sum_cm = int(raw) if raw is not None else 0

        return AnticheatWindow(
            player_id=player_id,
            since=since,
            organic_sum_cm=organic_sum_cm,
        )
