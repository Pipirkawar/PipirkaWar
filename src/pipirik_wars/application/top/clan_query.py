"""Порт `IClanTopQuery` (Спринт 2.2.A / ПД 2.2.1).

Запрос «дай мне топ-N кланов по сумме длин активных участников».
Реализуется кэшем `ClanTopCache` (in-memory с TTL=60s, аналогично
`TopPlayersCache`), который под капотом обращается к
`IClanRepository.list_top_by_total_length`. Отдельный порт нужен,
чтобы use-case `GetTopClans` не знал ни про кэш, ни про SQL —
он просто делегирует запрос.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from pipirik_wars.domain.clan import ClanTopEntry


class IClanTopQuery(abc.ABC):
    """Источник топа кланов (с кэшированием или без)."""

    @abc.abstractmethod
    async def get_top(self, *, limit: int) -> Sequence[ClanTopEntry]:
        """Топ-`limit` кланов (отсортирован, от самого «длинного» к короткому).

        Контракт реализаций:
        - возвращает не более `limit` элементов;
        - элементы упорядочены по убыванию `total_length_cm`,
          тай-брейкер — `clan_id ASC` (стабильный порядок);
        - в выборке только `ACTIVE`-кланы и только `ACTIVE`-игроки;
        - кланы без активных участников исключаются;
        - кэширующая реализация может возвращать «протухшие» данные в
          пределах своего TTL — это by design.
        """
