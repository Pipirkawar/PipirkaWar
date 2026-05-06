"""Use-case `GetClanAttackHistory` (Спринт 2.2.G / ПД 2.2.5).

Тонкая обёртка над `IClanMassDuelHistoryQuery`: валидирует
`clan_id` / `limit`, отдаёт sequence для презентера. Сам запрос
живёт за портом — use-case не знает, есть ли там SQL, кэш или
что-то ещё.

ПД 2.2.5: журнал клановых атак (история боёв в карточке клана).
По аналогии с `GetTopClans` (Спринт 2.2.A) — read-only, без
кэша (журнал per-clan, низкая частота запросов). Default-лимит
выбран `10`: последние 10 боёв укладываются в один Telegram-
сообщение и закрывают типичный use-case «что было недавно».
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.application.pvp.clan_history_query import IClanMassDuelHistoryQuery
from pipirik_wars.domain.pvp import ClanMassDuelHistoryEntry


class GetClanAttackHistory:
    """Use-case чтения журнала клановых атак."""

    __slots__ = ("_default_limit", "_query")

    def __init__(
        self,
        *,
        query: IClanMassDuelHistoryQuery,
        default_limit: int = 10,
    ) -> None:
        if default_limit <= 0:
            raise ValueError(f"default_limit must be positive, got {default_limit}")
        self._query = query
        self._default_limit = default_limit

    async def execute(
        self,
        *,
        clan_id: int,
        limit: int | None = None,
    ) -> Sequence[ClanMassDuelHistoryEntry]:
        """Получить журнал массовых боёв клана.

        `limit=None` → используется `default_limit`. `clan_id` должен
        быть положительным; реализация порта `IClanMassDuelHistoryQuery`
        отдаёт пустую последовательность для несуществующего клана
        (журнал — read-only-проекция, без отдельной валидации
        существования клана).
        """
        if clan_id <= 0:
            raise ValueError(f"clan_id must be positive, got {clan_id}")
        effective_limit = self._default_limit if limit is None else limit
        if effective_limit <= 0:
            raise ValueError(f"limit must be positive, got {effective_limit}")
        return await self._query.get_recent(clan_id=clan_id, limit=effective_limit)
