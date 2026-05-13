"""Юнит-тесты настроек канала анонсов (Спринт 4.9)."""

from __future__ import annotations

from pipirik_wars.infrastructure.settings.settings import BotSettings


class TestAnnouncementSettings:
    def test_defaults(self) -> None:
        settings = BotSettings()
        assert settings.announcement_channel_id is None
        assert settings.announcement_weekly_enabled is True
        assert settings.announcement_weekly_cron == "0 12 * * 1"

    def test_channel_id_set(self) -> None:
        settings = BotSettings(
            announcement_channel_id=12345,
        )
        assert settings.announcement_channel_id == 12345

    def test_weekly_disabled(self) -> None:
        settings = BotSettings(
            announcement_weekly_enabled=False,
        )
        assert settings.announcement_weekly_enabled is False

    def test_custom_cron(self) -> None:
        settings = BotSettings(
            announcement_weekly_cron="30 18 * * 5",
        )
        assert settings.announcement_weekly_cron == "30 18 * * 5"
