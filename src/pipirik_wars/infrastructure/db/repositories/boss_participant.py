"""Реализация `IBossParticipantRepository` поверх `boss_participants` (3.3-B).

Сериализация участника рейд-боя :class:`BossParticipant`:

* `participant.is_summoner` ↔ `is_summoner: bool`. На БД-уровне инвариант
  «у одного боя ≤ одного саммонера» защищён partial-unique-индексом
  `uq_boss_participants_one_summoner_per_boss_fight`.
* `participant.length_at_join_cm` ↔ `length_at_join_cm: int > 0`
  (CHECK `ck_boss_participants_length_positive`).
* timestamp проходит через `ensure_utc()`.

Босс рейд-боя в `boss_participants`-таблицу **не пишется** — он на
`boss_fights.boss_player_id`. Здесь только саммонер + рейдеры
(см. ГДД §10.3).

Все БД-уровневые `IntegrityError`-ы (UNIQUE / CHECK / FK) преобразуются
в доменный `IntegrityError` из `pipirik_wars.shared.errors`.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.bosses import (
    BossParticipant,
    IBossParticipantRepository,
)
from pipirik_wars.infrastructure.db.models import BossParticipantORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _row_to_entity(row: BossParticipantORM) -> BossParticipant:
    return BossParticipant(
        boss_fight_id=row.boss_fight_id,
        player_id=row.player_id,
        is_summoner=row.is_summoner,
        length_at_join_cm=row.length_at_join_cm,
        joined_at=ensure_utc(row.joined_at),
    )


class SqlAlchemyBossParticipantRepository(IBossParticipantRepository):
    """SQLAlchemy-реализация `IBossParticipantRepository` (см. domain-port)."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, participant: BossParticipant) -> BossParticipant:
        row = BossParticipantORM(
            boss_fight_id=participant.boss_fight_id,
            player_id=participant.player_id,
            is_summoner=participant.is_summoner,
            length_at_join_cm=participant.length_at_join_cm,
            joined_at=participant.joined_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add boss_participant for boss_fight_id={participant.boss_fight_id} "
                f"player_id={participant.player_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row)

    async def list_by_boss_fight(
        self,
        *,
        boss_fight_id: int,
    ) -> tuple[BossParticipant, ...]:
        result = await self._uow.session.execute(
            select(BossParticipantORM)
            .where(BossParticipantORM.boss_fight_id == boss_fight_id)
            .order_by(BossParticipantORM.joined_at, BossParticipantORM.player_id),
        )
        return tuple(_row_to_entity(row) for row in result.scalars().all())

    async def get_by_boss_fight_and_player(
        self,
        *,
        boss_fight_id: int,
        player_id: int,
    ) -> BossParticipant | None:
        result = await self._uow.session.execute(
            select(BossParticipantORM).where(
                BossParticipantORM.boss_fight_id == boss_fight_id,
                BossParticipantORM.player_id == player_id,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)

    async def remove(self, *, boss_fight_id: int, player_id: int) -> None:
        await self._uow.session.execute(
            delete(BossParticipantORM).where(
                BossParticipantORM.boss_fight_id == boss_fight_id,
                BossParticipantORM.player_id == player_id,
            ),
        )


__all__ = ["SqlAlchemyBossParticipantRepository"]
