"""Use-case `PublishWeeklyDigest` (Спринт 4.9, ГДД §1.2 backlog).

Собирает данные за прошедшую неделю и публикует дайджест в
Telegram-канал анонсов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.announcements.stats_query import (
    IAnnouncementStatsQuery,
)
from pipirik_wars.application.top.clan_query import IClanTopQuery
from pipirik_wars.application.top.entries import TopPlayerEntry
from pipirik_wars.application.top.query import ITopPlayersQuery
from pipirik_wars.domain.announcements.entities import (
    ClanWeeklyEntry,
    PlayerWeeklyEntry,
    WeeklyDigest,
)
from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher
from pipirik_wars.domain.shared.ports import IClock

logger = logging.getLogger(__name__)

_TOP_PLAYERS_LIMIT = 10
_TOP_CLANS_LIMIT = 5


def _render_digest(digest: WeeklyDigest) -> str:
    """Render weekly digest as HTML message for Telegram."""
    lines: list[str] = []
    start = digest.period_start.strftime("%d.%m")
    end = digest.period_end.strftime("%d.%m.%Y")
    lines.append(
        f"\U0001f4ca <b>Итоги недели #{digest.week_number}</b> ({start} \u2014 {end})",
    )
    lines.append("")

    # Top players
    lines.append("\U0001f3c6 <b>Топ-10 Пипириков:</b>")
    for i, p in enumerate(digest.top_players, 1):
        lines.append(f"{i}. {p.name} \u2014 {p.length_cm} см")
    lines.append("")

    # Top clans
    lines.append("\U0001f6e1 <b>Топ-5 Племён:</b>")
    for i, c in enumerate(digest.top_clans, 1):
        lines.append(
            f"{i}. {c.title} \u2014 {c.total_length_cm} см ({c.member_count} \U0001f465)",
        )
    lines.append("")

    # Player of the week
    if digest.player_of_week_name:
        lines.append(
            f"\u2b50 <b>Игрок недели:</b> {digest.player_of_week_name} "
            f"(+{digest.player_of_week_growth} см)",
        )
    # Clan of the week
    if digest.clan_of_week_title:
        lines.append(
            f"\U0001f3c5 <b>Племя недели:</b> {digest.clan_of_week_title} "
            f"(+{digest.clan_of_week_growth} см)",
        )
    lines.append("")

    # Stats
    lines.append("\U0001f4c8 <b>Статистика:</b>")
    lines.append(f"\u2022 Новых игроков: {digest.new_registrations}")
    lines.append(f"\u2022 Походов в лес: {digest.forest_runs}")
    lines.append(f"\u2022 Дуэлей: {digest.duels}")
    lines.append(f"\u2022 Караванов: {digest.caravans}")
    lines.append(f"\u2022 Рейдов: {digest.raids}")
    lines.append("")
    lines.append("\U0001f346 Pipirik Wars \u2014 присоединяйся!")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PublishWeeklyDigestResult:
    """Результат публикации еженедельного дайджеста."""

    digest: WeeklyDigest
    rendered_text: str


class PublishWeeklyDigest:
    """Собирает данные за неделю и публикует дайджест в канал."""

    __slots__ = (
        "_clans_query",
        "_clock",
        "_players_query",
        "_publisher",
        "_stats_query",
    )

    def __init__(
        self,
        *,
        publisher: IAnnouncementPublisher,
        players_query: ITopPlayersQuery,
        clans_query: IClanTopQuery,
        stats_query: IAnnouncementStatsQuery,
        clock: IClock,
    ) -> None:
        self._publisher = publisher
        self._players_query = players_query
        self._clans_query = clans_query
        self._stats_query = stats_query
        self._clock = clock

    async def execute(self, *, channel_id: int) -> PublishWeeklyDigestResult:
        """Собрать и опубликовать еженедельный дайджест."""
        today = self._clock.now().date()
        period_end = today - timedelta(days=1)
        period_start = period_end - timedelta(days=6)
        week_number = period_end.isocalendar()[1]

        top_players_raw = await self._players_query.get_top(
            limit=_TOP_PLAYERS_LIMIT,
        )
        top_clans_raw = await self._clans_query.get_top(limit=_TOP_CLANS_LIMIT)

        stats = await self._stats_query.weekly_stats(
            period_start=period_start,
            period_end=period_end,
        )

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

        digest = WeeklyDigest(
            week_number=week_number,
            period_start=period_start,
            period_end=period_end,
            top_players=top_players,
            top_clans=top_clans,
            player_of_week_name=(stats.player_of_week.name if stats.player_of_week else None),
            player_of_week_growth=(stats.player_of_week.growth_cm if stats.player_of_week else 0),
            clan_of_week_title=(stats.clan_of_week.title if stats.clan_of_week else None),
            clan_of_week_growth=(stats.clan_of_week.growth_cm if stats.clan_of_week else 0),
            new_registrations=stats.new_registrations,
            forest_runs=stats.forest_runs,
            duels=stats.duels,
            caravans=stats.caravans,
            raids=stats.raids,
        )

        rendered = _render_digest(digest)
        await self._publisher.publish(channel_id, rendered)
        logger.info(
            "weekly_digest_published",
            extra={"channel_id": channel_id, "week": week_number},
        )
        return PublishWeeklyDigestResult(digest=digest, rendered_text=rendered)


def _format_player_name(entry: TopPlayerEntry) -> str:
    """Format a TopPlayerEntry for display in the digest."""
    parts: list[str] = []
    if entry.title is not None:
        parts.append(str(entry.title))
    parts.append(str(entry.display_name))
    if entry.name is not None:
        parts.append(str(entry.name))
    return " ".join(parts) if parts else "Безымянный"
