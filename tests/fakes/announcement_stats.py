"""In-memory фейк для `IAnnouncementStatsQuery` (Спринт 4.9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from pipirik_wars.application.announcements.stats_query import (
    ClanGrowthRow,
    IAnnouncementStatsQuery,
    PlayerGrowthRow,
    WeeklyStatsRow,
)


@dataclass
class FakeAnnouncementStatsQuery(IAnnouncementStatsQuery):
    """Возвращает заранее заданную статистику."""

    result: WeeklyStatsRow = field(
        default_factory=lambda: WeeklyStatsRow(
            new_registrations=42,
            forest_runs=100,
            duels=50,
            caravans=10,
            raids=5,
            player_of_week=PlayerGrowthRow(name="TestPlayer", growth_cm=345),
            clan_of_week=ClanGrowthRow(title="TestClan", growth_cm=890),
        ),
    )
    calls: list[tuple[date, date]] = field(default_factory=list)

    async def weekly_stats(
        self,
        *,
        period_start: date,
        period_end: date,
    ) -> WeeklyStatsRow:
        self.calls.append((period_start, period_end))
        return self.result
