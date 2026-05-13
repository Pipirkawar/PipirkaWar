"""Сущности и value-objects для канала анонсов (Спринт 4.9)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PlayerWeeklyEntry:
    """Один ряд игрока в еженедельном дайджесте."""

    name: str
    length_cm: int


@dataclass(frozen=True, slots=True)
class ClanWeeklyEntry:
    """Один ряд клана в еженедельном дайджесте."""

    title: str
    total_length_cm: int
    member_count: int


@dataclass(frozen=True, slots=True)
class WeeklyDigest:
    """Еженедельный дайджест для канала анонсов."""

    week_number: int
    period_start: date
    period_end: date
    top_players: tuple[PlayerWeeklyEntry, ...]
    top_clans: tuple[ClanWeeklyEntry, ...]
    player_of_week_name: str | None
    player_of_week_growth: int
    clan_of_week_title: str | None
    clan_of_week_growth: int
    new_registrations: int
    forest_runs: int
    duels: int
    caravans: int
    raids: int


@dataclass(frozen=True, slots=True)
class LeaderboardSnapshot:
    """Текущий лидерборд для публикации в канал."""

    top_players: tuple[PlayerWeeklyEntry, ...]
    top_clans: tuple[ClanWeeklyEntry, ...]
