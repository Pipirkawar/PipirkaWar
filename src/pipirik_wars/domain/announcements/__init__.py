"""Домен «Канал-анонсы» (Спринт 4.9, ГДД §1.2 backlog).

Публикация контента в публичный Telegram-канал бота:
еженедельный дайджест, лидерборд-снапшот.
"""

from __future__ import annotations

from pipirik_wars.domain.announcements.entities import (
    LeaderboardSnapshot,
    WeeklyDigest,
)
from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher

__all__ = [
    "IAnnouncementPublisher",
    "LeaderboardSnapshot",
    "WeeklyDigest",
]
