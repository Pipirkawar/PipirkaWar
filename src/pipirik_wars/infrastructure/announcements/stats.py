"""SQL-реализация `IAnnouncementStatsQuery` (Спринт 4.9).

Агрегирует данные из нескольких таблиц (users, forest_runs,
pvp_duels, caravans, boss_fights, audit_log) за заданный период.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipirik_wars.application.announcements.stats_query import (
    ClanGrowthRow,
    IAnnouncementStatsQuery,
    PlayerGrowthRow,
    WeeklyStatsRow,
)
from pipirik_wars.infrastructure.db.models.boss import BossFightORM
from pipirik_wars.infrastructure.db.models.caravan import CaravanORM
from pipirik_wars.infrastructure.db.models.clan import ClanMemberORM, ClanORM
from pipirik_wars.infrastructure.db.models.forest import ForestRunORM
from pipirik_wars.infrastructure.db.models.player import UserORM
from pipirik_wars.infrastructure.db.models.pvp import PvpDuelORM
from pipirik_wars.infrastructure.db.models.security import AuditLogORM


def _date_to_utc_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _date_to_utc_end(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=UTC)


class SqlAlchemyAnnouncementStatsQuery(IAnnouncementStatsQuery):
    """SQL-реализация сбора статистики за неделю."""

    __slots__ = ("_session_factory",)

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def weekly_stats(
        self,
        *,
        period_start: date,
        period_end: date,
    ) -> WeeklyStatsRow:
        async with self._session_factory() as session:
            return await self._collect(
                session,
                period_start=period_start,
                period_end=period_end,
            )

    async def _collect(
        self,
        session: AsyncSession,
        *,
        period_start: date,
        period_end: date,
    ) -> WeeklyStatsRow:
        start_dt = _date_to_utc_start(period_start)
        end_dt = _date_to_utc_end(period_end)

        new_regs = await self._count_new_registrations(
            session,
            start_dt,
            end_dt,
        )
        forest_count = await self._count_forest_runs(
            session,
            start_dt,
            end_dt,
        )
        duel_count = await self._count_duels(session, start_dt, end_dt)
        caravan_count = await self._count_caravans(session, start_dt, end_dt)
        raid_count = await self._count_raids(session, start_dt, end_dt)
        player_of_week = await self._player_of_week(
            session,
            start_dt,
            end_dt,
        )
        clan_of_week = await self._clan_of_week(session, start_dt, end_dt)

        return WeeklyStatsRow(
            new_registrations=new_regs,
            forest_runs=forest_count,
            duels=duel_count,
            caravans=caravan_count,
            raids=raid_count,
            player_of_week=player_of_week,
            clan_of_week=clan_of_week,
        )

    @staticmethod
    async def _count_new_registrations(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> int:
        result = await session.execute(
            select(func.count(UserORM.id)).where(
                UserORM.created_at >= start,
                UserORM.created_at <= end,
            ),
        )
        return int(result.scalar_one())

    @staticmethod
    async def _count_forest_runs(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> int:
        result = await session.execute(
            select(func.count(ForestRunORM.id)).where(
                ForestRunORM.started_at >= start,
                ForestRunORM.started_at <= end,
            ),
        )
        return int(result.scalar_one())

    @staticmethod
    async def _count_duels(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> int:
        result = await session.execute(
            select(func.count(PvpDuelORM.id)).where(
                PvpDuelORM.created_at >= start,
                PvpDuelORM.created_at <= end,
            ),
        )
        return int(result.scalar_one())

    @staticmethod
    async def _count_caravans(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> int:
        result = await session.execute(
            select(func.count(CaravanORM.id)).where(
                CaravanORM.started_at >= start,
                CaravanORM.started_at <= end,
            ),
        )
        return int(result.scalar_one())

    @staticmethod
    async def _count_raids(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> int:
        result = await session.execute(
            select(func.count(BossFightORM.id)).where(
                BossFightORM.started_at >= start,
                BossFightORM.started_at <= end,
            ),
        )
        return int(result.scalar_one())

    @staticmethod
    async def _player_of_week(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> PlayerGrowthRow | None:
        """Player with max total positive delta_cm via audit_log."""
        stmt = (
            select(
                AuditLogORM.target_id,
                func.sum(AuditLogORM.delta_cm).label("growth"),
            )
            .where(
                AuditLogORM.occurred_at >= start,
                AuditLogORM.occurred_at <= end,
                AuditLogORM.target_kind == "player",
                AuditLogORM.delta_cm.isnot(None),
                AuditLogORM.delta_cm > 0,
            )
            .group_by(AuditLogORM.target_id)
            .order_by(func.sum(AuditLogORM.delta_cm).desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        player_id_str: str = row[0]
        growth: int = int(row[1])
        player_result = await session.execute(
            select(UserORM.username, UserORM.name).where(
                UserORM.id == int(player_id_str),
            ),
        )
        player_row = player_result.first()
        name = "Безымянный"
        if player_row is not None:
            name = player_row[1] or player_row[0] or "Безымянный"
        return PlayerGrowthRow(name=name, growth_cm=growth)

    @staticmethod
    async def _clan_of_week(
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> ClanGrowthRow | None:
        """Clan with max summed growth of members via audit_log."""
        stmt = (
            select(
                ClanMemberORM.clan_id,
                func.sum(AuditLogORM.delta_cm).label("growth"),
            )
            .select_from(AuditLogORM)
            .join(
                ClanMemberORM,
                ClanMemberORM.player_id
                == func.cast(
                    AuditLogORM.target_id,
                    ClanMemberORM.player_id.type,
                ),
            )
            .where(
                AuditLogORM.occurred_at >= start,
                AuditLogORM.occurred_at <= end,
                AuditLogORM.target_kind == "player",
                AuditLogORM.delta_cm.isnot(None),
                AuditLogORM.delta_cm > 0,
            )
            .group_by(ClanMemberORM.clan_id)
            .order_by(func.sum(AuditLogORM.delta_cm).desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        clan_id: int = int(row[0])
        growth: int = int(row[1])
        clan_result = await session.execute(
            select(ClanORM.title).where(ClanORM.id == clan_id),
        )
        clan_row = clan_result.first()
        title = "Безымянное племя"
        if clan_row is not None and clan_row[0] is not None:
            title = clan_row[0]
        return ClanGrowthRow(title=title, growth_cm=growth)
