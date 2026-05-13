"""Порт запроса статистики для еженедельного дайджеста (Спринт 4.9).

Живёт в application-слое (не domain), потому что собирает
агрегированные данные из нескольких доменных сущностей — это
read-side query, а не доменная бизнес-логика.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PlayerGrowthRow:
    """Игрок с максимальным приростом длины за период."""

    name: str
    growth_cm: int


@dataclass(frozen=True, slots=True)
class ClanGrowthRow:
    """Клан с максимальным приростом суммарной длины за период."""

    title: str
    growth_cm: int


@dataclass(frozen=True, slots=True)
class WeeklyStatsRow:
    """Агрегированная статистика за неделю."""

    new_registrations: int
    forest_runs: int
    duels: int
    caravans: int
    raids: int
    player_of_week: PlayerGrowthRow | None
    clan_of_week: ClanGrowthRow | None


class IAnnouncementStatsQuery(abc.ABC):
    """Read-side запрос статистики для еженедельного дайджеста."""

    @abc.abstractmethod
    async def weekly_stats(
        self,
        *,
        period_start: date,
        period_end: date,
    ) -> WeeklyStatsRow:
        """Собрать агрегированную статистику за период [start, end]."""
