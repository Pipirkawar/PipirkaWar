"""Реализация `ICaravanRepository` поверх таблицы `caravans` (Спринт 3.2-B).

Сериализация агрегата :class:`Caravan`:

* `caravan.status` (`CaravanStatus`) ↔ строка из CHECK-whitelist-а
  (`'lobby' | 'in_battle' | 'finished' | 'cancelled'`);
* timestamp-поля проходят через `ensure_utc()` — БД может вернуть
  `naive`-datetime для SQLite, `tz-aware` — для Postgres; домен
  всегда работает в UTC.
* partial-unique `(sender_clan_id) WHERE status IN ('lobby', 'in_battle')`
  гарантирует на БД-уровне «один активный караван на клан-отправителя»;
  use-case `CreateCaravan` дополнительно охраняет инвариант через
  application-level чек.

Все БД-уровневые `IntegrityError`-ы (нарушение CHECK / FK / UNIQUE)
конвертируются в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanStatus,
    ICaravanRepository,
)
from pipirik_wars.infrastructure.db.models import CaravanORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

# Статусы, при которых караван считается «активным» (ещё не завершён,
# ещё не отменён). Используются и в partial-unique-индексе, и в
# `get_active_by_clan(...)`.
_ACTIVE_STATUSES: tuple[str, ...] = (
    CaravanStatus.LOBBY.value,
    CaravanStatus.IN_BATTLE.value,
)


def _row_to_entity(row: CaravanORM) -> Caravan:
    return Caravan(
        id=row.id,
        sender_clan_id=row.sender_clan_id,
        receiver_clan_id=row.receiver_clan_id,
        leader_player_id=row.leader_player_id,
        status=CaravanStatus(row.status),
        started_at=ensure_utc(row.started_at),
        lobby_ends_at=ensure_utc(row.lobby_ends_at),
        battle_ends_at=ensure_utc(row.battle_ends_at),
        random_seed=row.random_seed,
        finished_at=ensure_utc(row.finished_at) if row.finished_at is not None else None,
    )


class SqlAlchemyCaravanRepository(ICaravanRepository):
    """SQLAlchemy-реализация `ICaravanRepository` (см. domain-port)."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, caravan: Caravan) -> Caravan:
        if caravan.id is not None:
            raise DomainIntegrityError(
                f"Caravan with pre-set id={caravan.id} cannot be added; use save()"
            )
        row = CaravanORM(
            sender_clan_id=caravan.sender_clan_id,
            receiver_clan_id=caravan.receiver_clan_id,
            leader_player_id=caravan.leader_player_id,
            status=caravan.status.value,
            started_at=caravan.started_at,
            lobby_ends_at=caravan.lobby_ends_at,
            battle_ends_at=caravan.battle_ends_at,
            random_seed=caravan.random_seed,
            finished_at=caravan.finished_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add caravan for sender_clan_id={caravan.sender_clan_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)

    async def get_by_id(self, *, caravan_id: int) -> Caravan | None:
        row = await self._uow.session.get(CaravanORM, caravan_id)
        if row is None:
            return None
        return _row_to_entity(row)

    async def get_active_by_clan(self, *, clan_id: int) -> Caravan | None:
        result = await self._uow.session.execute(
            select(CaravanORM).where(
                CaravanORM.sender_clan_id == clan_id,
                CaravanORM.status.in_(_ACTIVE_STATUSES),
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)

    async def get_last_finished_at_for_clan(self, *, clan_id: int) -> datetime | None:
        # «Кулдаун» по ГДД §9.3 считается от `started_at` последнего
        # каравана клана-отправителя — независимо от статуса (включая
        # отменённые). Берём максимум `started_at` по `sender_clan_id`.
        result = await self._uow.session.execute(
            select(CaravanORM.started_at)
            .where(CaravanORM.sender_clan_id == clan_id)
            .order_by(desc(CaravanORM.started_at))
            .limit(1),
        )
        last = result.scalar_one_or_none()
        if last is None:
            return None
        return ensure_utc(last)

    async def save(self, caravan: Caravan) -> Caravan:
        if caravan.id is None:
            raise DomainIntegrityError("Caravan.save requires id; use add() for new caravans")
        result = await self._uow.session.execute(
            select(CaravanORM).where(CaravanORM.id == caravan.id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise DomainIntegrityError(f"Caravan id={caravan.id} not found")
        row.sender_clan_id = caravan.sender_clan_id
        row.receiver_clan_id = caravan.receiver_clan_id
        row.leader_player_id = caravan.leader_player_id
        row.status = caravan.status.value
        row.started_at = caravan.started_at
        row.lobby_ends_at = caravan.lobby_ends_at
        row.battle_ends_at = caravan.battle_ends_at
        row.random_seed = caravan.random_seed
        row.finished_at = caravan.finished_at
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save caravan id={caravan.id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)


__all__ = ["SqlAlchemyCaravanRepository"]
