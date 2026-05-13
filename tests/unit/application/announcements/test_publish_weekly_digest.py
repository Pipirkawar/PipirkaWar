"""Юнит-тесты use-case `PublishWeeklyDigest` (Спринт 4.9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.announcements.publish_weekly_digest import (
    PublishWeeklyDigest,
    _render_digest,
)
from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.domain.announcements.entities import (
    ClanWeeklyEntry,
    PlayerWeeklyEntry,
    WeeklyDigest,
)
from pipirik_wars.domain.clan import ClanTopEntry
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.player import DisplayName
from tests.fakes import (
    FakeAnnouncementPublisher,
    FakeAnnouncementStatsQuery,
    FakeClanTopQuery,
    FakeClock,
    FakeTopPlayersQuery,
)


def _player(name: str, length: int) -> TopPlayerEntry:
    return TopPlayerEntry(
        title=None,
        display_name=DisplayName(value=name),
        name=None,
        length_cm=length,
    )


def _clan(title: str, total: int, count: int) -> ClanTopEntry:
    return ClanTopEntry(
        clan_id=1,
        clan_title=ClanTitle(value=title),
        total_length_cm=total,
        member_count=count,
    )


class TestPublishWeeklyDigest:
    @pytest.mark.asyncio
    async def test_execute_publishes_digest(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[_player("Player1", 100)])
        clans_q = FakeClanTopQuery(rows=[_clan("Clan1", 500, 5)])
        stats_q = FakeAnnouncementStatsQuery()
        clock = FakeClock(datetime(2026, 5, 12, 12, 0, tzinfo=UTC))  # Monday

        uc = PublishWeeklyDigest(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
            stats_query=stats_q,
            clock=clock,
        )

        result = await uc.execute(channel_id=123)

        assert len(publisher.calls) == 1
        assert publisher.calls[0][0] == 123
        assert "Итоги недели" in result.rendered_text
        assert result.digest.new_registrations == 42

    @pytest.mark.asyncio
    async def test_digest_contains_player_of_week(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[_player("TopGuy", 999)])
        clans_q = FakeClanTopQuery(rows=[])
        stats_q = FakeAnnouncementStatsQuery()
        clock = FakeClock(datetime(2026, 5, 12, 12, 0, tzinfo=UTC))

        uc = PublishWeeklyDigest(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
            stats_query=stats_q,
            clock=clock,
        )

        result = await uc.execute(channel_id=456)
        text = result.rendered_text
        assert "Игрок недели" in text
        assert "TestPlayer" in text
        assert "+345 см" in text

    @pytest.mark.asyncio
    async def test_digest_contains_clan_of_week(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[])
        clans_q = FakeClanTopQuery(rows=[_clan("MyClan", 1000, 10)])
        stats_q = FakeAnnouncementStatsQuery()
        clock = FakeClock(datetime(2026, 5, 12, 12, 0, tzinfo=UTC))

        uc = PublishWeeklyDigest(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
            stats_query=stats_q,
            clock=clock,
        )

        result = await uc.execute(channel_id=789)
        text = result.rendered_text
        assert "Племя недели" in text
        assert "TestClan" in text
        assert "+890 см" in text

    @pytest.mark.asyncio
    async def test_digest_stats_section(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[])
        clans_q = FakeClanTopQuery(rows=[])
        stats_q = FakeAnnouncementStatsQuery()
        clock = FakeClock(datetime(2026, 5, 12, 12, 0, tzinfo=UTC))

        uc = PublishWeeklyDigest(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
            stats_query=stats_q,
            clock=clock,
        )

        result = await uc.execute(channel_id=111)
        text = result.rendered_text
        assert "Новых игроков: 42" in text
        assert "Походов в лес: 100" in text
        assert "Дуэлей: 50" in text
        assert "Караванов: 10" in text
        assert "Рейдов: 5" in text

    @pytest.mark.asyncio
    async def test_digest_period_dates(self) -> None:
        publisher = FakeAnnouncementPublisher()
        clock = FakeClock(datetime(2026, 5, 12, 12, 0, tzinfo=UTC))

        uc = PublishWeeklyDigest(
            publisher=publisher,
            players_query=FakeTopPlayersQuery(rows=[]),
            clans_query=FakeClanTopQuery(rows=[]),
            stats_query=FakeAnnouncementStatsQuery(),
            clock=clock,
        )

        result = await uc.execute(channel_id=111)
        # period_end = May 11, period_start = May 5
        assert result.digest.period_start.month == 5
        assert result.digest.period_start.day == 5
        assert result.digest.period_end.month == 5
        assert result.digest.period_end.day == 11


class TestRenderDigest:
    def test_renders_full_digest(self) -> None:
        digest = WeeklyDigest(
            week_number=20,
            period_start=__import__("datetime").date(2026, 5, 5),
            period_end=__import__("datetime").date(2026, 5, 11),
            top_players=(
                PlayerWeeklyEntry(name="Player1", length_cm=100),
                PlayerWeeklyEntry(name="Player2", length_cm=50),
            ),
            top_clans=(ClanWeeklyEntry(title="Clan1", total_length_cm=500, member_count=5),),
            player_of_week_name="Player1",
            player_of_week_growth=50,
            clan_of_week_title="Clan1",
            clan_of_week_growth=200,
            new_registrations=10,
            forest_runs=20,
            duels=5,
            caravans=3,
            raids=1,
        )
        text = _render_digest(digest)
        assert "<b>Итоги недели #20</b>" in text
        assert "Player1" in text
        assert "100 см" in text
        assert "Pipirik Wars" in text

    def test_renders_without_player_of_week(self) -> None:
        digest = WeeklyDigest(
            week_number=1,
            period_start=__import__("datetime").date(2026, 1, 1),
            period_end=__import__("datetime").date(2026, 1, 7),
            top_players=(),
            top_clans=(),
            player_of_week_name=None,
            player_of_week_growth=0,
            clan_of_week_title=None,
            clan_of_week_growth=0,
            new_registrations=0,
            forest_runs=0,
            duels=0,
            caravans=0,
            raids=0,
        )
        text = _render_digest(digest)
        assert "Игрок недели" not in text
        assert "Племя недели" not in text
