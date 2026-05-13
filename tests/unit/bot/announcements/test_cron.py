"""Юнит-тесты cron-matching для announcement scheduler (Спринт 4.9)."""

from __future__ import annotations

from datetime import UTC, datetime

from pipirik_wars.bot.main import _cron_field_matches, _cron_matches


class TestCronFieldMatches:
    def test_star_matches_everything(self) -> None:
        assert _cron_field_matches("*", 0) is True
        assert _cron_field_matches("*", 59) is True

    def test_exact_value(self) -> None:
        assert _cron_field_matches("0", 0) is True
        assert _cron_field_matches("0", 1) is False
        assert _cron_field_matches("12", 12) is True

    def test_range(self) -> None:
        assert _cron_field_matches("1-5", 3) is True
        assert _cron_field_matches("1-5", 0) is False
        assert _cron_field_matches("1-5", 6) is False

    def test_step(self) -> None:
        assert _cron_field_matches("*/15", 0) is True
        assert _cron_field_matches("*/15", 15) is True
        assert _cron_field_matches("*/15", 30) is True
        assert _cron_field_matches("*/15", 7) is False

    def test_comma_list(self) -> None:
        assert _cron_field_matches("0,30", 0) is True
        assert _cron_field_matches("0,30", 30) is True
        assert _cron_field_matches("0,30", 15) is False


class TestCronMatches:
    def test_monday_noon(self) -> None:
        # "0 12 * * 1" — Monday 12:00
        dt = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)  # Monday
        assert _cron_matches("0 12 * * 1", dt) is True

    def test_monday_wrong_time(self) -> None:
        dt = datetime(2026, 5, 11, 13, 0, tzinfo=UTC)  # Monday 13:00
        assert _cron_matches("0 12 * * 1", dt) is False

    def test_tuesday_noon(self) -> None:
        dt = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)  # Tuesday
        assert _cron_matches("0 12 * * 1", dt) is False

    def test_invalid_cron(self) -> None:
        dt = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
        assert _cron_matches("invalid", dt) is False

    def test_sunday(self) -> None:
        dt = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)  # Sunday = 0
        assert _cron_matches("0 12 * * 0", dt) is True

    def test_every_minute(self) -> None:
        dt = datetime(2026, 5, 11, 12, 30, tzinfo=UTC)
        assert _cron_matches("* * * * *", dt) is True

    def test_specific_day_and_hour(self) -> None:
        dt = datetime(2026, 5, 15, 8, 0, tzinfo=UTC)  # Thursday
        assert _cron_matches("0 8 15 * *", dt) is True
