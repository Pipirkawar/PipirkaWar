"""Юнит-тесты use-case `GetTopPlayers` (Спринт 1.4.C / ПД 1.4.6)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.top import GetTopPlayers, TopPlayerEntry
from pipirik_wars.domain.player import DisplayName
from tests.fakes import FakeTopPlayersQuery


def _entry(length: int) -> TopPlayerEntry:
    return TopPlayerEntry(
        title=None,
        display_name=DisplayName(value=f"L{length}"),
        name=None,
        length_cm=length,
    )


class TestGetTopPlayers:
    @pytest.mark.asyncio
    async def test_default_limit_is_100(self) -> None:
        """Контракт ПД 1.4.6: топ-100 — дефолтный размер."""
        query = FakeTopPlayersQuery()
        uc = GetTopPlayers(query=query)
        await uc.execute()
        assert query.calls == [100]

    def test_default_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="default_limit"):
            GetTopPlayers(query=FakeTopPlayersQuery(), default_limit=0)
        with pytest.raises(ValueError, match="default_limit"):
            GetTopPlayers(query=FakeTopPlayersQuery(), default_limit=-1)

    @pytest.mark.asyncio
    async def test_execute_uses_default_when_limit_none(self) -> None:
        query = FakeTopPlayersQuery(rows=[_entry(100), _entry(50), _entry(10)])
        uc = GetTopPlayers(query=query, default_limit=2)

        result = await uc.execute()

        assert query.calls == [2]
        assert [e.length_cm for e in result] == [100, 50]

    @pytest.mark.asyncio
    async def test_execute_uses_explicit_limit(self) -> None:
        query = FakeTopPlayersQuery(rows=[_entry(100), _entry(50), _entry(10)])
        uc = GetTopPlayers(query=query, default_limit=100)

        result = await uc.execute(limit=2)

        assert query.calls == [2]
        assert [e.length_cm for e in result] == [100, 50]

    @pytest.mark.asyncio
    async def test_execute_rejects_non_positive_limit(self) -> None:
        uc = GetTopPlayers(query=FakeTopPlayersQuery())
        with pytest.raises(ValueError, match="limit"):
            await uc.execute(limit=0)
        with pytest.raises(ValueError, match="limit"):
            await uc.execute(limit=-5)

    @pytest.mark.asyncio
    async def test_execute_returns_empty_when_no_players(self) -> None:
        uc = GetTopPlayers(query=FakeTopPlayersQuery(rows=[]))

        result = await uc.execute(limit=100)

        assert result == ()
