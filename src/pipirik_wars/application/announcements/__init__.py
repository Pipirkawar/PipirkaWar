"""Application-слой анонсов (Спринт 4.9)."""

from __future__ import annotations

from pipirik_wars.application.announcements.publish_leaderboard import (
    PublishLeaderboard,
)
from pipirik_wars.application.announcements.publish_weekly_digest import (
    PublishWeeklyDigest,
)
from pipirik_wars.application.announcements.stats_query import (
    IAnnouncementStatsQuery,
    WeeklyStatsRow,
)

__all__ = [
    "IAnnouncementStatsQuery",
    "PublishLeaderboard",
    "PublishWeeklyDigest",
    "WeeklyStatsRow",
]
