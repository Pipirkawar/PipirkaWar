"""Aiogram-адаптер для `IAnnouncementPublisher` (Спринт 4.9)."""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Bot

from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher

_LOGGER: Final = logging.getLogger(__name__)


class AiogramAnnouncementPublisher(IAnnouncementPublisher):
    """Публикация через `Bot.send_message(channel_id, ...)`."""

    __slots__ = ("_bot",)

    def __init__(self, *, bot: Bot) -> None:
        self._bot = bot

    async def publish(
        self,
        channel_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> None:
        await self._bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=parse_mode,
        )
        _LOGGER.info(
            "announcement_published",
            extra={"channel_id": channel_id, "text_len": len(text)},
        )
