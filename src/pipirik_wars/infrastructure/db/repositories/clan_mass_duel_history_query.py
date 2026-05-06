"""SQL-реализация `IClanMassDuelHistoryQuery` (Спринт 2.2.G / ПД 2.2.5).

Читает журнал массовых боёв конкретного клана из `pvp_mass_duels`
с JOIN-ом к `clans` (для названия противника) и двумя коррелированными
подзапросами к `pvp_mass_duel_choices` (для подсчёта участников каждой
стороны). `IN_PROGRESS`-бои фильтруются на уровне SQL — журнал содержит
только завершённые/отменённые бои (in-progress нечего показывать).

Отдельная read-side-проекция (а не метод на `IMassDuelRepository`),
потому что:
- репозиторий-агрегат заботится о write-side и идемпотентном
  восстановлении агрегата из всех 3 таблиц (что для журнала из 100
  записей было бы лютой пессимизацией);
- VO `ClanMassDuelHistoryEntry` денормализован под рендер UI (наша
  сторона / противник / итог с нашей точки зрения), а не под
  доменный агрегат.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, func, select

from pipirik_wars.application.pvp.clan_history_query import IClanMassDuelHistoryQuery
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
    MassDuelState,
    MassDuelWinner,
)
from pipirik_wars.infrastructure.db.models import (
    ClanORM,
    PvpMassDuelChoiceORM,
    PvpMassDuelORM,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc

_CLAN1_SIDE = "clan1"
_CLAN2_SIDE = "clan2"


class SqlAlchemyClanMassDuelHistoryQuery(IClanMassDuelHistoryQuery):
    """Read-side SQL-проекция журнала клановых атак."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_recent(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[ClanMassDuelHistoryEntry]:
        if clan_id <= 0:
            raise ValueError(f"clan_id must be positive, got {clan_id}")
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")

        # `opponent_id`: если наш клан = clan1, противник = clan2, и наоборот.
        opponent_id = case(
            (PvpMassDuelORM.clan1_id == clan_id, PvpMassDuelORM.clan2_id),
            else_=PvpMassDuelORM.clan1_id,
        )

        # Коррелированные подзапросы — считаем участников каждой стороны.
        clan1_count = (
            select(func.count())
            .select_from(PvpMassDuelChoiceORM)
            .where(
                PvpMassDuelChoiceORM.duel_id == PvpMassDuelORM.id,
                PvpMassDuelChoiceORM.clan_side == _CLAN1_SIDE,
            )
            .correlate(PvpMassDuelORM)
            .scalar_subquery()
        )
        clan2_count = (
            select(func.count())
            .select_from(PvpMassDuelChoiceORM)
            .where(
                PvpMassDuelChoiceORM.duel_id == PvpMassDuelORM.id,
                PvpMassDuelChoiceORM.clan_side == _CLAN2_SIDE,
            )
            .correlate(PvpMassDuelORM)
            .scalar_subquery()
        )

        stmt = (
            select(
                PvpMassDuelORM.id.label("duel_id"),
                PvpMassDuelORM.clan1_id,
                PvpMassDuelORM.clan2_id,
                PvpMassDuelORM.state,
                PvpMassDuelORM.created_at,
                PvpMassDuelORM.completed_at,
                PvpMassDuelORM.final_winner,
                PvpMassDuelORM.final_clan1_total_dealt,
                PvpMassDuelORM.final_clan2_total_dealt,
                PvpMassDuelORM.final_clan1_delta_cm,
                PvpMassDuelORM.final_clan2_delta_cm,
                ClanORM.title.label("opponent_title"),
                clan1_count.label("clan1_count"),
                clan2_count.label("clan2_count"),
            )
            .join(ClanORM, ClanORM.id == opponent_id)
            .where(
                (PvpMassDuelORM.clan1_id == clan_id) | (PvpMassDuelORM.clan2_id == clan_id),
                PvpMassDuelORM.state.in_(("completed", "cancelled")),
            )
            .order_by(
                PvpMassDuelORM.created_at.desc(),
                PvpMassDuelORM.id.desc(),
            )
            .limit(limit)
        )
        result = await self._uow.session.execute(stmt)
        return tuple(_row_to_entry(row, clan_id=clan_id) for row in result.all())


def _row_to_entry(row: object, *, clan_id: int) -> ClanMassDuelHistoryEntry:
    """Маппит row из `select(...)` в `ClanMassDuelHistoryEntry`.

    `clan_id` нужен, чтобы определить нашу сторону боя (clan1 или
    clan2), и спроецировать `final_clan{1,2}_*` на «нашу/чужую»
    систему координат.
    """
    is_clan1 = row.clan1_id == clan_id  # type: ignore[attr-defined]
    if is_clan1:
        opponent_clan_id = row.clan2_id  # type: ignore[attr-defined]
        our_count = int(row.clan1_count)  # type: ignore[attr-defined]
        opponent_count = int(row.clan2_count)  # type: ignore[attr-defined]
        our_side = _CLAN1_SIDE
    else:
        opponent_clan_id = row.clan1_id  # type: ignore[attr-defined]
        our_count = int(row.clan2_count)  # type: ignore[attr-defined]
        opponent_count = int(row.clan1_count)  # type: ignore[attr-defined]
        our_side = _CLAN2_SIDE

    state = MassDuelState(row.state)  # type: ignore[attr-defined]
    is_completed = state is MassDuelState.COMPLETED

    if is_completed:
        winner = MassDuelWinner(row.final_winner)  # type: ignore[attr-defined]
        outcome = ClanMassDuelHistoryEntry.outcome_from_winner(
            winner=winner,
            our_side=our_side,
        )
        clan1_dealt = int(row.final_clan1_total_dealt)  # type: ignore[attr-defined]
        clan2_dealt = int(row.final_clan2_total_dealt)  # type: ignore[attr-defined]
        clan1_delta = int(row.final_clan1_delta_cm)  # type: ignore[attr-defined]
        clan2_delta = int(row.final_clan2_delta_cm)  # type: ignore[attr-defined]
        if is_clan1:
            our_total_dealt = clan1_dealt
            our_total_received = clan2_dealt
            our_delta_cm = clan1_delta
            opponent_delta_cm = clan2_delta
        else:
            our_total_dealt = clan2_dealt
            our_total_received = clan1_dealt
            our_delta_cm = clan2_delta
            opponent_delta_cm = clan1_delta
        completed_at = ensure_utc(row.completed_at)  # type: ignore[attr-defined]
    else:
        outcome = ClanMassDuelOutcomeForUs.CANCELLED
        our_total_dealt = 0
        our_total_received = 0
        our_delta_cm = 0
        opponent_delta_cm = 0
        completed_at = None

    return ClanMassDuelHistoryEntry(
        duel_id=int(row.duel_id),  # type: ignore[attr-defined]
        our_clan_id=clan_id,
        opponent_clan_id=int(opponent_clan_id),
        opponent_clan_title=ClanTitle(value=row.opponent_title),  # type: ignore[attr-defined]
        state=state,
        outcome=outcome,
        our_total_dealt=our_total_dealt,
        our_total_received=our_total_received,
        our_delta_cm=our_delta_cm,
        opponent_delta_cm=opponent_delta_cm,
        our_participants_count=our_count,
        opponent_participants_count=opponent_count,
        created_at=ensure_utc(row.created_at),  # type: ignore[attr-defined]
        completed_at=completed_at,
    )


__all__ = ["SqlAlchemyClanMassDuelHistoryQuery"]
