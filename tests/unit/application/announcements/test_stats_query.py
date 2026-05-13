"""Юнит-тесты `IAnnouncementStatsQuery` и `WeeklyStatsRow` (Спринт 4.9)."""

from __future__ import annotations

from datetime import date

import pytest

from pipirik_wars.application.announcements.stats_query import (
    ClanGrowthRow,
    IAnnouncementStatsQuery,
    PlayerGrowthRow,
    WeeklyStatsRow,
)
from tests.fakes import FakeAnnouncementStatsQuery


class TestWeeklyStatsRow:
    def test_creates_valid_row(self) -> None:
        row = WeeklyStatsRow(
            new_registrations=10,
            forest_runs=20,
            duels=5,
            caravans=3,
            raids=1,
            player_of_week=PlayerGrowthRow(name="Test", growth_cm=100),
            clan_of_week=ClanGrowthRow(title="TestClan", growth_cm=200),
        )
        assert row.new_registrations == 10
        assert row.player_of_week is not None
        assert row.player_of_week.name == "Test"

    def test_none_player_and_clan(self) -> None:
        row = WeeklyStatsRow(
            new_registrations=0,
            forest_runs=0,
            duels=0,
            caravans=0,
            raids=0,
            player_of_week=None,
            clan_of_week=None,
        )
        assert row.player_of_week is None
        assert row.clan_of_week is None


class TestFakeAnnouncementStatsQuery:
    def test_is_valid_implementation(self) -> None:
        query = FakeAnnouncementStatsQuery()
        assert isinstance(query, IAnnouncementStatsQuery)

    @pytest.mark.asyncio
    async def test_returns_configured_result(self) -> None:
        query = FakeAnnouncementStatsQuery()
        result = await query.weekly_stats(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 7),
        )
        assert result.new_registrations == 42
        assert len(query.calls) == 1
