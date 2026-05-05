"""Порт `ITopPlayersQuery` (Спринт 1.4.C / ПД 1.4.6).

Запрос «дай мне топ-N игроков по длине». Реализуется кэшем
`TopPlayersCache` (in-memory с TTL=60s), который под капотом
обращается к `IPlayerRepository.list_top_by_length`. Отдельный
порт нужен, чтобы use-case `GetTopPlayers` не знал ни про кэш,
ни про SQL — он просто делегирует запрос.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.application.top.entries import TopPlayerEntry


class ITopPlayersQuery(abc.ABC):
    """Источник топа игроков (с кэшированием или без)."""

    @abc.abstractmethod
    async def get_top(self, *, limit: int) -> Sequence[TopPlayerEntry]:
        """Топ-`limit` игроков (отсортирован, от самого длинного к короткому).

        Контракт реализаций:
        - возвращает не более `limit` элементов;
        - элементы упорядочены по убыванию `length_cm` (тай-брейкер
          определяется источником, обычно `id ASC`);
        - все элементы — `ACTIVE`-игроки;
        - кэширующая реализация может возвращать «протухшие» данные в
          пределах своего TTL, это by design.
        """
