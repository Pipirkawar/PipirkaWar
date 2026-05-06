"""In-memory фейки `IDailyHeadRepository` / `IDailyActivityRepository`.

Используются в юнит-тестах доменного `DailyHeadService` (Спринт 2.3.A)
и application use-case-ов 2.3.C (`RequestDailyHead` / `RunDailyHeadCron`)
без поднятия БД.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from pipirik_wars.domain.daily_head import (
    DailyHeadAssignment,
    IDailyActivityRepository,
    IDailyHeadRepository,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeDailyHeadRepository(IDailyHeadRepository):
    """In-memory таблица `daily_heads`."""

    items: list[DailyHeadAssignment] = field(default_factory=list)
    _next_id: int = 1

    async def get_by_clan_and_date(
        self,
        *,
        clan_id: int,
        moscow_date: date,
    ) -> DailyHeadAssignment | None:
        for entry in self.items:
            if entry.clan_id == clan_id and entry.moscow_date == moscow_date:
                return entry
        return None

    async def add(self, assignment: DailyHeadAssignment) -> DailyHeadAssignment:
        # БД-уровневая проверка UNIQUE-индекса.
        existing = await self.get_by_clan_and_date(
            clan_id=assignment.clan_id,
            moscow_date=assignment.moscow_date,
        )
        if existing is not None:
            raise IntegrityError(
                f"daily_heads UNIQUE violation on "
                f"(clan_id={assignment.clan_id}, "
                f"moscow_date={assignment.moscow_date.isoformat()})"
            )
        if assignment.id is None:
            saved = replace(assignment, id=self._next_id)
            self._next_id += 1
        else:
            saved = assignment
            self._next_id = max(self._next_id, assignment.id + 1)
        self.items.append(saved)
        return saved

    async def list_recent_for_clan(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[DailyHeadAssignment]:
        clan_items = [item for item in self.items if item.clan_id == clan_id]
        clan_items.sort(
            key=lambda x: (x.assigned_at, x.id or 0),
            reverse=True,
        )
        return tuple(clan_items[:limit])


@dataclass
class FakeDailyActivityRepository(IDailyActivityRepository):
    """In-memory активность участников клана.

    Тест задаёт словарь `{clan_id: [player_id, ...]}` — все они
    считаются «активными» за окно. Логика «within_days» в фейке
    не воспроизводится, тест явно подменяет данные.
    """

    by_clan: dict[int, list[int]] = field(default_factory=dict)
    calls: list[tuple[int, int]] = field(default_factory=list)

    async def list_active_member_ids(
        self,
        *,
        clan_id: int,
        within_days: int,
    ) -> Sequence[int]:
        self.calls.append((clan_id, within_days))
        return tuple(self.by_clan.get(clan_id, []))


__all__ = [
    "FakeDailyActivityRepository",
    "FakeDailyHeadRepository",
]
