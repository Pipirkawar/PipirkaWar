"""In-memory фейк для `IClanTopQuery` (Спринт 2.2.A)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.top import ClanTopEntry, IClanTopQuery


@dataclass
class FakeClanTopQuery(IClanTopQuery):
    """Возвращает заранее заданный список, считая вызовы.

    Полезен в тестах handler-а и use-case-а, чтобы проверить сам
    маршрут «handler → use-case → query» без реальной БД.
    """

    rows: list[ClanTopEntry] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)

    async def get_top(self, *, limit: int) -> Sequence[ClanTopEntry]:
        self.calls.append(limit)
        return tuple(self.rows[:limit])
