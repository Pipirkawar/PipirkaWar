"""Integration-тесты `SqlAlchemyOracleHistoryRepository` (Спринт 1.4.B)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from pipirik_wars.domain.oracle import OracleInvocation
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyOracleHistoryRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
TODAY_MOSCOW = date(2026, 5, 5)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyOracleHistoryRepository:
    return SqlAlchemyOracleHistoryRepository(uow=uow)


def _invocation(
    *,
    player_id: int,
    moscow_date: date = TODAY_MOSCOW,
    bonus_cm: int = 7,
    template_id: str = "oracle.ru.0001",
    occurred_at: datetime = NOW,
) -> OracleInvocation:
    return OracleInvocation(
        player_id=player_id,
        moscow_date=moscow_date,
        bonus_cm=bonus_cm,
        template_id=template_id,
        occurred_at=occurred_at,
    )


class TestSqlAlchemyOracleHistoryRepository:
    @pytest.mark.asyncio
    async def test_add_then_get_for_day(self, uow: SqlAlchemyUnitOfWork) -> None:
        player = await _seed_player(uow, tg_id=100)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(_invocation(player_id=player.id))

        async with uow:
            got = await repo.get_for_day(player_id=player.id, moscow_date=TODAY_MOSCOW)

        assert got is not None
        assert got.player_id == player.id
        assert got.moscow_date == TODAY_MOSCOW
        assert got.bonus_cm == 7
        assert got.template_id == "oracle.ru.0001"
        # ensure_utc применяется на чтении.
        assert got.occurred_at == NOW

    @pytest.mark.asyncio
    async def test_get_for_day_returns_none_when_missing(self, uow: SqlAlchemyUnitOfWork) -> None:
        player = await _seed_player(uow, tg_id=100)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            got = await repo.get_for_day(player_id=player.id, moscow_date=TODAY_MOSCOW)

        assert got is None

    @pytest.mark.asyncio
    async def test_unique_player_id_moscow_date(self, uow: SqlAlchemyUnitOfWork) -> None:
        player = await _seed_player(uow, tg_id=100)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(_invocation(player_id=player.id))

        # Повторный INSERT с тем же ключом должен упасть на commit-е UoW.
        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(_invocation(player_id=player.id, bonus_cm=10))

    @pytest.mark.asyncio
    async def test_two_players_same_day_independent(self, uow: SqlAlchemyUnitOfWork) -> None:
        a = await _seed_player(uow, tg_id=100)
        b = await _seed_player(uow, tg_id=200)
        assert a.id is not None and b.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(_invocation(player_id=a.id))
            await repo.add(_invocation(player_id=b.id))

        async with uow:
            ga = await repo.get_for_day(player_id=a.id, moscow_date=TODAY_MOSCOW)
            gb = await repo.get_for_day(player_id=b.id, moscow_date=TODAY_MOSCOW)

        assert ga is not None and gb is not None
        assert ga.player_id == a.id and gb.player_id == b.id

    @pytest.mark.asyncio
    async def test_same_player_different_days_independent(self, uow: SqlAlchemyUnitOfWork) -> None:
        player = await _seed_player(uow, tg_id=100)
        assert player.id is not None
        repo = _make_repo(uow)
        day_b = date(2026, 5, 6)

        async with uow:
            await repo.add(_invocation(player_id=player.id, moscow_date=TODAY_MOSCOW))
            await repo.add(
                _invocation(
                    player_id=player.id,
                    moscow_date=day_b,
                    template_id="oracle.ru.0002",
                )
            )

        async with uow:
            day_a_record = await repo.get_for_day(player_id=player.id, moscow_date=TODAY_MOSCOW)
            day_b_record = await repo.get_for_day(player_id=player.id, moscow_date=day_b)

        assert day_a_record is not None
        assert day_b_record is not None
        assert day_a_record.template_id != day_b_record.template_id
