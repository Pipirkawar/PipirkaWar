"""In-memory \u0444\u0435\u0439\u043a \u0434\u043b\u044f `IClanMassDuelHistoryQuery` (\u0421\u043f\u0440\u0438\u043d\u0442 2.2.G / \u041f\u0414 2.2.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.application.pvp import IClanMassDuelHistoryQuery
from pipirik_wars.domain.pvp import ClanMassDuelHistoryEntry


@dataclass
class FakeClanMassDuelHistoryQuery(IClanMassDuelHistoryQuery):
    """\u0412\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 \u0437\u0430\u0440\u0430\u043d\u0435\u0435 \u0437\u0430\u0434\u0430\u043d\u043d\u044b\u0439 \u0441\u043b\u043e\u0432\u0430\u0440\u044c `clan_id -> entries`,\n\u0441\u0447\u0438\u0442\u0430\u0435\u0442 \u0432\u044b\u0437\u043e\u0432\u044b. \u041f\u043e\u043b\u0435\u0437\u0435\u043d \u0432 \u0442\u0435\u0441\u0442\u0430\u0445 use-case-\u0430 \u0431\u0435\u0437 \u0440\u0435\u0430\u043b\u044c\u043d\u043e\u0439 \u0411\u0414."""

    by_clan: dict[int, list[ClanMassDuelHistoryEntry]] = field(default_factory=dict)
    calls: list[tuple[int, int]] = field(default_factory=list)

    async def get_recent(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[ClanMassDuelHistoryEntry]:
        self.calls.append((clan_id, limit))
        return tuple(self.by_clan.get(clan_id, [])[:limit])


__all__ = ["FakeClanMassDuelHistoryQuery"]
