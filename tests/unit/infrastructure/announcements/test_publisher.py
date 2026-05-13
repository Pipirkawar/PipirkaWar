"""Юнит-тесты `AiogramAnnouncementPublisher` (Спринт 4.9)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher
from pipirik_wars.infrastructure.announcements.publisher import (
    AiogramAnnouncementPublisher,
)


class TestAiogramAnnouncementPublisher:
    def test_is_valid_implementation(self) -> None:
        bot = AsyncMock()
        publisher = AiogramAnnouncementPublisher(bot=bot)
        assert isinstance(publisher, IAnnouncementPublisher)

    @pytest.mark.asyncio
    async def test_publish_calls_send_message(self) -> None:
        bot = AsyncMock()
        publisher = AiogramAnnouncementPublisher(bot=bot)

        await publisher.publish(123, "test message", "HTML")

        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="test message",
            parse_mode="HTML",
        )

    @pytest.mark.asyncio
    async def test_publish_default_parse_mode(self) -> None:
        bot = AsyncMock()
        publisher = AiogramAnnouncementPublisher(bot=bot)

        await publisher.publish(456, "test message")

        bot.send_message.assert_awaited_once_with(
            chat_id=456,
            text="test message",
            parse_mode="HTML",
        )
