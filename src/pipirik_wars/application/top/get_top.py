"""Use-case `GetTopPlayers` (Спринт 1.4.C / ПД 1.4.6).

Тонкая обёртка над `ITopPlayersQuery`: приводит вход к
DTO-DTO-семантике, валидирует `limit`, отдаёт sequence для
презентера. Сам кэш живёт за портом — use-case не знает,
есть ли там TTL, in-memory, Redis или просто прямой запрос к БД.

ПД 1.4.6: топ-100 по длине, кэш TTL=60s.
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.application.top.entries import TopPlayerEntry
from pipirik_wars.application.top.query import ITopPlayersQuery


class GetTopPlayers:
    """Use-case чтения топа игроков."""

    __slots__ = ("_default_limit", "_query")

    def __init__(
        self,
        *,
        query: ITopPlayersQuery,
        default_limit: int = 100,
    ) -> None:
        if default_limit <= 0:
            raise ValueError(f"default_limit must be positive, got {default_limit}")
        self._query = query
        self._default_limit = default_limit

    async def execute(self, *, limit: int | None = None) -> Sequence[TopPlayerEntry]:
        """Получить топ. `limit=None` → используется `default_limit` (=100)."""
        effective_limit = self._default_limit if limit is None else limit
        if effective_limit <= 0:
            raise ValueError(f"limit must be positive, got {effective_limit}")
        return await self._query.get_top(limit=effective_limit)
