"""Порт публикации анонсов в канал (Спринт 4.9)."""

from __future__ import annotations

import abc


class IAnnouncementPublisher(abc.ABC):
    """Отправка сообщения в Telegram-канал анонсов."""

    @abc.abstractmethod
    async def publish(
        self,
        channel_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> None:
        """Опубликовать текст в указанный канал."""
