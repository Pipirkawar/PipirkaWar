"""Юнит-тесты use-case `PublishLeaderboard` (Спринт 4.9)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.announcements.publish_leaderboard import (
    PublishLeaderboard,
    _render_leaderboard,
)
from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.domain.announcements.entities import (
    ClanWeeklyEntry,
    LeaderboardSnapshot,
    PlayerWeeklyEntry,
)
from pipirik_wars.domain.clan import ClanTopEntry
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.player import DisplayName
from tests.fakes import (
    FakeAnnouncementPublisher,
    FakeClanTopQuery,
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


class TestPublishLeaderboard:
    @pytest.mark.asyncio
    async def test_execute_publishes_leaderboard(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(
            rows=[_player("Player1", 100), _player("Player2", 50)],
        )
        clans_q = FakeClanTopQuery(rows=[_clan("Clan1", 500, 5)])

        uc = PublishLeaderboard(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
        )

        result = await uc.execute(channel_id=123)

        assert len(publisher.calls) == 1
        assert publisher.calls[0][0] == 123
        assert "лидерборд" in result.rendered_text.lower()
        assert len(result.snapshot.top_players) == 2
        assert len(result.snapshot.top_clans) == 1

    @pytest.mark.asyncio
    async def test_leaderboard_contains_players(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[_player("Alpha", 999)])
        clans_q = FakeClanTopQuery(rows=[])

        uc = PublishLeaderboard(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
        )

        result = await uc.execute(channel_id=456)
        assert "Alpha" in result.rendered_text
        assert "999 см" in result.rendered_text

    @pytest.mark.asyncio
    async def test_leaderboard_empty_data(self) -> None:
        publisher = FakeAnnouncementPublisher()
        players_q = FakeTopPlayersQuery(rows=[])
        clans_q = FakeClanTopQuery(rows=[])

        uc = PublishLeaderboard(
            publisher=publisher,
            players_query=players_q,
            clans_query=clans_q,
        )

        result = await uc.execute(channel_id=789)
        assert len(publisher.calls) == 1
        assert len(result.snapshot.top_players) == 0


class TestRenderLeaderboard:
    def test_renders_populated_snapshot(self) -> None:
        snapshot = LeaderboardSnapshot(
            top_players=(PlayerWeeklyEntry(name="Player1", length_cm=100),),
            top_clans=(ClanWeeklyEntry(title="Clan1", total_length_cm=500, member_count=5),),
        )
        text = _render_leaderboard(snapshot)
        assert "лидерборд" in text.lower()
        assert "Player1" in text
        assert "100 см" in text
        assert "Clan1" in text
        assert "500 см" in text
        assert "Pipirik Wars" in text

    def test_renders_empty_snapshot(self) -> None:
        snapshot = LeaderboardSnapshot(top_players=(), top_clans=())
        text = _render_leaderboard(snapshot)
        assert "лидерборд" in text.lower()
