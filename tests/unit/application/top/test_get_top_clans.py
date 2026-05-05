"""Юнит-тесты use-case `GetTopClans` (Спринт 2.2.A / ПД 2.2.1)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.top import ClanTopEntry, GetTopClans
from pipirik_wars.domain.clan import ClanTitle
from tests.fakes import FakeClanTopQuery


def _entry(*, clan_id: int = 1, total: int = 100, members: int = 3) -> ClanTopEntry:
    return ClanTopEntry(
        clan_id=clan_id,
        clan_title=ClanTitle(f"Клан-{clan_id}"),
        total_length_cm=total,
        member_count=members,
    )


class TestGetTopClans:
    @pytest.mark.asyncio
    async def test_default_limit_is_50(self) -> None:
        """Контракт ПД 2.2.1: дефолтный размер /clantop — 50."""
        query = FakeClanTopQuery()
        uc = GetTopClans(query=query)
        await uc.execute()
        assert query.calls == [50]

    def test_default_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="default_limit"):
            GetTopClans(query=FakeClanTopQuery(), default_limit=0)
        with pytest.raises(ValueError, match="default_limit"):
            GetTopClans(query=FakeClanTopQuery(), default_limit=-1)

    @pytest.mark.asyncio
    async def test_execute_uses_default_when_limit_none(self) -> None:
        rows = [_entry(clan_id=1, total=300), _entry(clan_id=2, total=150)]
        query = FakeClanTopQuery(rows=rows)
        uc = GetTopClans(query=query, default_limit=2)

        result = await uc.execute()

        assert query.calls == [2]
        assert [e.clan_id for e in result] == [1, 2]

    @pytest.mark.asyncio
    async def test_execute_uses_explicit_limit(self) -> None:
        rows = [_entry(clan_id=i, total=100 - i * 10) for i in range(1, 6)]
        query = FakeClanTopQuery(rows=rows)
        uc = GetTopClans(query=query, default_limit=50)

        result = await uc.execute(limit=2)

        assert query.calls == [2]
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_execute_rejects_non_positive_limit(self) -> None:
        uc = GetTopClans(query=FakeClanTopQuery())
        with pytest.raises(ValueError, match="limit"):
            await uc.execute(limit=0)
        with pytest.raises(ValueError, match="limit"):
            await uc.execute(limit=-5)

    @pytest.mark.asyncio
    async def test_execute_returns_empty_when_no_clans(self) -> None:
        uc = GetTopClans(query=FakeClanTopQuery(rows=[]))
        result = await uc.execute(limit=50)
        assert result == ()
