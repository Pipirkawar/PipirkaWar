"""Use-case `PublishLeaderboard` (Спринт 4.9, ГДД §1.2 backlog).

Публикует текущий лидерборд в Telegram-канал анонсов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pipirik_wars.application.announcements.publish_weekly_digest import (
    _format_player_name,
)
from pipirik_wars.application.top.clan_query import IClanTopQuery
from pipirik_wars.application.top.query import ITopPlayersQuery
from pipirik_wars.domain.announcements.entities import (
    ClanWeeklyEntry,
    LeaderboardSnapshot,
    PlayerWeeklyEntry,
)
from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher

logger = logging.getLogger(__name__)

_TOP_PLAYERS_LIMIT = 10
_TOP_CLANS_LIMIT = 5


def _render_leaderboard(snapshot: LeaderboardSnapshot) -> str:
    """Render leaderboard snapshot as HTML message for Telegram."""
    lines: list[str] = []
    lines.append("\U0001f3c6 <b>Текущий лидерборд</b>")
    lines.append("")

    lines.append("\U0001f451 <b>Топ-10 Пипириков:</b>")
    for i, p in enumerate(snapshot.top_players, 1):
        lines.append(f"{i}. {p.name} \u2014 {p.length_cm} см")
    lines.append("")

    lines.append("\U0001f6e1 <b>Топ-5 Племён:</b>")
    for i, c in enumerate(snapshot.top_clans, 1):
        lines.append(
            f"{i}. {c.title} \u2014 {c.total_length_cm} см ({c.member_count} \U0001f465)",
        )
    lines.append("")
    lines.append("\U0001f346 Pipirik Wars \u2014 присоединяйся!")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PublishLeaderboardResult:
    """Результат публикации лидерборда."""

    snapshot: LeaderboardSnapshot
    rendered_text: str


class PublishLeaderboard:
    """Публикует текущий лидерборд в канал анонсов."""

    __slots__ = ("_clans_query", "_players_query", "_publisher")

    def __init__(
        self,
        *,
        publisher: IAnnouncementPublisher,
        players_query: ITopPlayersQuery,
        clans_query: IClanTopQuery,
    ) -> None:
        self._publisher = publisher
        self._players_query = players_query
        self._clans_query = clans_query

    async def execute(self, *, channel_id: int) -> PublishLeaderboardResult:
        """Собрать и опубликовать лидерборд."""
        top_players_raw = await self._players_query.get_top(
            limit=_TOP_PLAYERS_LIMIT,
        )
        top_clans_raw = await self._clans_query.get_top(limit=_TOP_CLANS_LIMIT)

        top_players = tuple(
            PlayerWeeklyEntry(
                name=_format_player_name(p),
                length_cm=p.length_cm,
            )
            for p in top_players_raw
        )
        top_clans = tuple(
            ClanWeeklyEntry(
                title=str(c.clan_title),
                total_length_cm=c.total_length_cm,
                member_count=c.member_count,
            )
            for c in top_clans_raw
        )

        snapshot = LeaderboardSnapshot(
            top_players=top_players,
            top_clans=top_clans,
        )

        rendered = _render_leaderboard(snapshot)
        await self._publisher.publish(channel_id, rendered)
        logger.info(
            "leaderboard_published",
            extra={"channel_id": channel_id},
        )
        return PublishLeaderboardResult(
            snapshot=snapshot,
            rendered_text=rendered,
        )
