"""Юнит-тесты domain/announcements entities/VOs (Спринт 4.9)."""

from __future__ import annotations

from datetime import date

from pipirik_wars.domain.announcements.entities import (
    ClanWeeklyEntry,
    LeaderboardSnapshot,
    PlayerWeeklyEntry,
    WeeklyDigest,
)


class TestPlayerWeeklyEntry:
    def test_creates_valid_entry(self) -> None:
        entry = PlayerWeeklyEntry(name="TestPlayer", length_cm=100)
        assert entry.name == "TestPlayer"
        assert entry.length_cm == 100

    def test_frozen(self) -> None:
        entry = PlayerWeeklyEntry(name="TestPlayer", length_cm=100)
        assert entry.name == "TestPlayer"


class TestClanWeeklyEntry:
    def test_creates_valid_entry(self) -> None:
        entry = ClanWeeklyEntry(
            title="TestClan",
            total_length_cm=500,
            member_count=5,
        )
        assert entry.title == "TestClan"
        assert entry.total_length_cm == 500
        assert entry.member_count == 5


class TestWeeklyDigest:
    def test_creates_valid_digest(self) -> None:
        digest = WeeklyDigest(
            week_number=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 7),
            top_players=(PlayerWeeklyEntry(name="P1", length_cm=100),),
            top_clans=(ClanWeeklyEntry(title="C1", total_length_cm=500, member_count=5),),
            player_of_week_name="P1",
            player_of_week_growth=50,
            clan_of_week_title="C1",
            clan_of_week_growth=200,
            new_registrations=10,
            forest_runs=20,
            duels=5,
            caravans=3,
            raids=1,
        )
        assert digest.week_number == 1
        assert len(digest.top_players) == 1
        assert len(digest.top_clans) == 1

    def test_none_player_and_clan_of_week(self) -> None:
        digest = WeeklyDigest(
            week_number=2,
            period_start=date(2026, 1, 8),
            period_end=date(2026, 1, 14),
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
        assert digest.player_of_week_name is None
        assert digest.clan_of_week_title is None


class TestLeaderboardSnapshot:
    def test_creates_empty_snapshot(self) -> None:
        snapshot = LeaderboardSnapshot(top_players=(), top_clans=())
        assert len(snapshot.top_players) == 0
        assert len(snapshot.top_clans) == 0

    def test_creates_populated_snapshot(self) -> None:
        snapshot = LeaderboardSnapshot(
            top_players=(
                PlayerWeeklyEntry(name="P1", length_cm=100),
                PlayerWeeklyEntry(name="P2", length_cm=80),
            ),
            top_clans=(ClanWeeklyEntry(title="C1", total_length_cm=500, member_count=5),),
        )
        assert len(snapshot.top_players) == 2
        assert len(snapshot.top_clans) == 1
