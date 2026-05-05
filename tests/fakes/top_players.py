"""In-memory фейк для `ITopPlayersQuery` (Спринт 1.4.C)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.top import ITopPlayersQuery, TopPlayerEntry


@dataclass
class FakeTopPlayersQuery(ITopPlayersQuery):
    """Возвращает заранее заданный список, считая вызовы.

    Полезен в тестах handler-а и use-case-а, чтобы проверить сам
    маршрут «handler → use-case → query» без реальной БД.
    """

    rows: list[TopPlayerEntry] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)

    async def get_top(self, *, limit: int) -> Sequence[TopPlayerEntry]:
        self.calls.append(limit)
        return tuple(self.rows[:limit])
