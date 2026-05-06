"""Тесты для use-case `GetClanAttackHistory` (Спринт 2.2.G / ПД 2.2.5).

Use-case — тонкая обёртка: проверяем валидацию входов, дефолтный
лимит и проброс в `IClanMassDuelHistoryQuery.get_recent`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.pvp import (
    GetClanAttackHistory,
    IClanMassDuelHistoryQuery,
)
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
    MassDuelState,
)


class _FakeHistoryQuery(IClanMassDuelHistoryQuery):
    def __init__(self, entries: Sequence[ClanMassDuelHistoryEntry] = ()) -> None:
        self._entries = entries
        self.calls: list[tuple[int, int]] = []

    async def get_recent(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[ClanMassDuelHistoryEntry]:
        self.calls.append((clan_id, limit))
        return tuple(self._entries[:limit])


def _make_entry(duel_id: int = 1) -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=duel_id,
        our_clan_id=100,
        opponent_clan_id=200,
        opponent_clan_title=ClanTitle("Жмыхи"),
        state=MassDuelState.COMPLETED,
        outcome=ClanMassDuelOutcomeForUs.VICTORY,
        our_total_dealt=30,
        our_total_received=10,
        our_delta_cm=20,
        opponent_delta_cm=-20,
        our_participants_count=3,
        opponent_participants_count=3,
        created_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
    )


class TestGetClanAttackHistory:
    async def test_returns_query_result(self) -> None:
        entry = _make_entry()
        query = _FakeHistoryQuery(entries=[entry])
        use_case = GetClanAttackHistory(query=query, default_limit=10)
        result = await use_case.execute(clan_id=100)
        assert tuple(result) == (entry,)
        assert query.calls == [(100, 10)]

    async def test_uses_default_limit_when_none(self) -> None:
        query = _FakeHistoryQuery()
        use_case = GetClanAttackHistory(query=query, default_limit=42)
        await use_case.execute(clan_id=5)
        assert query.calls == [(5, 42)]

    async def test_uses_explicit_limit_when_provided(self) -> None:
        query = _FakeHistoryQuery()
        use_case = GetClanAttackHistory(query=query, default_limit=10)
        await use_case.execute(clan_id=5, limit=3)
        assert query.calls == [(5, 3)]

    async def test_truncates_to_limit(self) -> None:
        entries = [_make_entry(duel_id=i) for i in (1, 2, 3, 4, 5)]
        query = _FakeHistoryQuery(entries=entries)
        use_case = GetClanAttackHistory(query=query, default_limit=10)
        result = await use_case.execute(clan_id=100, limit=2)
        assert tuple(e.duel_id for e in result) == (1, 2)

    async def test_empty_clan_returns_empty(self) -> None:
        query = _FakeHistoryQuery(entries=[])
        use_case = GetClanAttackHistory(query=query, default_limit=10)
        result = await use_case.execute(clan_id=100)
        assert tuple(result) == ()

    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_default_limit_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="default_limit must be positive"):
            GetClanAttackHistory(query=_FakeHistoryQuery(), default_limit=bad)

    @pytest.mark.parametrize("bad", [0, -1])
    async def test_clan_id_must_be_positive(self, bad: int) -> None:
        use_case = GetClanAttackHistory(query=_FakeHistoryQuery(), default_limit=10)
        with pytest.raises(ValueError, match="clan_id must be positive"):
            await use_case.execute(clan_id=bad)

    @pytest.mark.parametrize("bad", [0, -1])
    async def test_explicit_limit_must_be_positive(self, bad: int) -> None:
        use_case = GetClanAttackHistory(query=_FakeHistoryQuery(), default_limit=10)
        with pytest.raises(ValueError, match="limit must be positive"):
            await use_case.execute(clan_id=100, limit=bad)
