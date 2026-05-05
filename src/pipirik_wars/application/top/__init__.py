"""Топ игроков и кланов (Спринт 1.4.C / 2.2.A; ПД 1.4.6 / ПД 2.2.1).

Публичный API:
- `TopPlayerEntry` — DTO одной записи топа игроков.
- `ITopPlayersQuery` — порт «дай топ-N игроков» (реализуется кэшем).
- `GetTopPlayers` — use-case `/top`.
- `IClanTopQuery` — порт «дай топ-N кланов» (реализуется кэшем).
- `GetTopClans` — use-case `/clantop`.
- `ClanTopEntry` — re-export из `domain/clan/` для удобства handler-ов.
"""

from __future__ import annotations

from pipirik_wars.application.top.clan_query import IClanTopQuery
from pipirik_wars.application.top.entries import TopPlayerEntry
from pipirik_wars.application.top.get_top import GetTopPlayers
from pipirik_wars.application.top.get_top_clans import GetTopClans
from pipirik_wars.application.top.query import ITopPlayersQuery
from pipirik_wars.domain.clan import ClanTopEntry

__all__ = [
    "ClanTopEntry",
    "GetTopClans",
    "GetTopPlayers",
    "IClanTopQuery",
    "ITopPlayersQuery",
    "TopPlayerEntry",
]
