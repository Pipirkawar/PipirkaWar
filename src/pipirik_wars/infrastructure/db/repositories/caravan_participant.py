"""Реализация `ICaravanParticipantRepository` поверх `caravan_participants`.

Сериализация участника каравана :class:`CaravanParticipant`:

* `participant.role` (`CaravanRole`) ↔ строка из CHECK-whitelist-а
  (`'caravaneer' | 'defender' | 'raider'`); `LEADER`-роль на БД-уровне
  не существует — лидерство кодируется булевым флагом `is_leader`
  поверх `role='caravaneer'` (см. CHECK
  `ck_caravan_participants_leader_implies_caravaneer`).
* `participant.contribution` (`CaravanContribution | None`) ↔
  `contribution_cm: int | None` — `caravaneer` обязан хранить взнос
  `> 0`, `defender`/`raider` — обязан `NULL`
  (CHECK `ck_caravan_participants_contribution_matches_role`).
* timestamp проходит через `ensure_utc()`.

Все БД-уровневые `IntegrityError`-ы (UNIQUE / CHECK / FK) преобразуются
в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.caravan import (
    CaravanContribution,
    CaravanParticipant,
    CaravanRole,
    ICaravanParticipantRepository,
)
from pipirik_wars.infrastructure.db.models import CaravanParticipantORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _row_to_entity(row: CaravanParticipantORM) -> CaravanParticipant:
    contribution = (
        CaravanContribution(cm=row.contribution_cm) if row.contribution_cm is not None else None
    )
    return CaravanParticipant(
        caravan_id=row.caravan_id,
        player_id=row.player_id,
        role=CaravanRole(row.role),
        is_leader=row.is_leader,
        contribution=contribution,
        joined_at=ensure_utc(row.joined_at),
    )


class SqlAlchemyCaravanParticipantRepository(ICaravanParticipantRepository):
    """SQLAlchemy-реализация `ICaravanParticipantRepository` (см. domain-port)."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, participant: CaravanParticipant) -> CaravanParticipant:
        row = CaravanParticipantORM(
            caravan_id=participant.caravan_id,
            player_id=participant.player_id,
            role=participant.role.value,
            is_leader=participant.is_leader,
            contribution_cm=(
                participant.contribution.cm if participant.contribution is not None else None
            ),
            joined_at=participant.joined_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add caravan_participant for caravan_id={participant.caravan_id} "
                f"player_id={participant.player_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)

    async def list_by_caravan(
        self,
        *,
        caravan_id: int,
    ) -> tuple[CaravanParticipant, ...]:
        result = await self._uow.session.execute(
            select(CaravanParticipantORM)
            .where(CaravanParticipantORM.caravan_id == caravan_id)
            .order_by(CaravanParticipantORM.player_id),
        )
        return tuple(_row_to_entity(row) for row in result.scalars().all())

    async def list_by_caravan_and_role(
        self,
        *,
        caravan_id: int,
        role: CaravanRole,
    ) -> tuple[CaravanParticipant, ...]:
        result = await self._uow.session.execute(
            select(CaravanParticipantORM)
            .where(
                CaravanParticipantORM.caravan_id == caravan_id,
                CaravanParticipantORM.role == role.value,
            )
            .order_by(CaravanParticipantORM.player_id),
        )
        return tuple(_row_to_entity(row) for row in result.scalars().all())

    async def remove(self, *, caravan_id: int, player_id: int) -> None:
        await self._uow.session.execute(
            delete(CaravanParticipantORM).where(
                CaravanParticipantORM.caravan_id == caravan_id,
                CaravanParticipantORM.player_id == player_id,
            ),
        )


__all__ = ["SqlAlchemyCaravanParticipantRepository"]
