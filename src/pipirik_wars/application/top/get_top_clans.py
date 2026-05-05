"""Use-case `GetTopClans` (Спринт 2.2.A / ПД 2.2.1).

Тонкая обёртка над `IClanTopQuery`: валидирует `limit`, отдаёт
sequence для презентера. Сам кэш живёт за портом — use-case не
знает, есть ли там TTL, in-memory, Redis или просто прямой запрос
к БД.

ПД 2.2.1: топ кланов по сумме длин активных участников. По аналогии
с `GetTopPlayers` (Спринт 1.4.C) — read-only, кэш TTL=60s. Дефолтный
лимит выбран меньше, чем у `/top` (100): кланов всегда заметно
меньше, чем игроков, и UI-страницы Telegram-сообщений ограничены ~50
строк. Точное значение можно править через DI без правки use-case-а.
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.application.top.clan_query import IClanTopQuery
from pipirik_wars.domain.clan import ClanTopEntry


class GetTopClans:
    """Use-case чтения топа кланов."""

    __slots__ = ("_default_limit", "_query")

    def __init__(
        self,
        *,
        query: IClanTopQuery,
        default_limit: int = 50,
    ) -> None:
        if default_limit <= 0:
            raise ValueError(f"default_limit must be positive, got {default_limit}")
        self._query = query
        self._default_limit = default_limit

    async def execute(self, *, limit: int | None = None) -> Sequence[ClanTopEntry]:
        """Получить топ кланов. `limit=None` → используется `default_limit`."""
        effective_limit = self._default_limit if limit is None else limit
        if effective_limit <= 0:
            raise ValueError(f"limit must be positive, got {effective_limit}")
        return await self._query.get_top(limit=effective_limit)
