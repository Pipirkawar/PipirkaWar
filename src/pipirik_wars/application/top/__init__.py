"""Топ игроков (Спринт 1.4.C / ПД 1.4.6).

Публичный API:
- `TopPlayerEntry` — DTO одной записи топа.
- `ITopPlayersQuery` — порт «дай топ-N» (реализуется кэшем).
- `GetTopPlayers` — use-case.
"""

from __future__ import annotations

from pipirik_wars.application.top.entries import TopPlayerEntry
from pipirik_wars.application.top.get_top import GetTopPlayers
from pipirik_wars.application.top.query import ITopPlayersQuery

__all__ = [
    "GetTopPlayers",
    "ITopPlayersQuery",
    "TopPlayerEntry",
]
