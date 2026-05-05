"""Integration-тесты `SqlAlchemyGlobalLobbyRepository` (Спринт 2.1.F).

Покрывают:

* enqueue / pop_oldest round-trip с FIFO-упорядочиванием;
* идемпотентность повторного enqueue (первоначальный `enqueued_at`
  не двигается);
* remove существующей и несуществующей записи;
* is_in_lobby для существующей и несуществующей записи;
* CASCADE-удаление лобби-записи при удалении дуэли.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.player import Player
from pipirik_wars.domain.pvp import Duel, DuelMode
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyDuelRepository,
    SqlAlchemyGlobalLobbyRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


async def _seed_pending_duel(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> int:
    """Завести pending GLOBAL_ONLY-дуэль и вернуть её PK."""

    players = SqlAlchemyPlayerRepository(uow=uow)
    duels = SqlAlchemyDuelRepository(uow=uow)
    async with uow:
        challenger = await players.add(Player.new(tg_id=tg_id, username=None, now=NOW))
        assert challenger.id is not None
        duel = Duel.create_challenge(
            challenger_id=challenger.id,
            challenged_id=None,
            mode=DuelMode.GLOBAL_ONLY,
            hit_pct=10,
            expected_rounds=3,
            now=NOW,
        )
        stored = await duels.add(duel)
    assert stored.id is not None
    return stored.id


class TestEnqueuePopOldest:
    @pytest.mark.asyncio
    async def test_enqueue_then_pop_returns_same_entry(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        duel_id = await _seed_pending_duel(uow, tg_id=1)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            ok = await repo.enqueue(duel_id=duel_id, enqueued_at=NOW)
            assert ok is True
            entry = await repo.pop_oldest()
        assert entry is not None
        assert entry.duel_id == duel_id
        assert entry.enqueued_at == NOW

    @pytest.mark.asyncio
    async def test_pop_oldest_empty_returns_none(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            entry = await repo.pop_oldest()
        assert entry is None

    @pytest.mark.asyncio
    async def test_pop_oldest_fifo_ordering(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Заводим 3 дуэли и кладём в лобби в обратном временном порядке —
        # pop_oldest обязан вернуть самую раннюю по `enqueued_at`.
        d1 = await _seed_pending_duel(uow, tg_id=1)
        d2 = await _seed_pending_duel(uow, tg_id=2)
        d3 = await _seed_pending_duel(uow, tg_id=3)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)

        async with uow:
            await repo.enqueue(duel_id=d2, enqueued_at=NOW + timedelta(seconds=2))
            await repo.enqueue(duel_id=d1, enqueued_at=NOW + timedelta(seconds=1))
            await repo.enqueue(duel_id=d3, enqueued_at=NOW + timedelta(seconds=3))
            first = await repo.pop_oldest()
            second = await repo.pop_oldest()
            third = await repo.pop_oldest()
            fourth = await repo.pop_oldest()
        assert first is not None and first.duel_id == d1
        assert second is not None and second.duel_id == d2
        assert third is not None and third.duel_id == d3
        assert fourth is None


class TestIdempotentEnqueue:
    @pytest.mark.asyncio
    async def test_repeat_enqueue_keeps_first_timestamp(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        duel_id = await _seed_pending_duel(uow, tg_id=1)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        first_ts = NOW
        second_ts = NOW + timedelta(minutes=5)

        async with uow:
            first = await repo.enqueue(duel_id=duel_id, enqueued_at=first_ts)
            second = await repo.enqueue(duel_id=duel_id, enqueued_at=second_ts)
            popped = await repo.pop_oldest()

        assert first is True
        assert second is False
        assert popped is not None
        assert popped.enqueued_at == first_ts


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_existing_entry(self, uow: SqlAlchemyUnitOfWork) -> None:
        duel_id = await _seed_pending_duel(uow, tg_id=1)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            await repo.enqueue(duel_id=duel_id, enqueued_at=NOW)
            removed = await repo.remove(duel_id=duel_id)
            still_in = await repo.is_in_lobby(duel_id=duel_id)
        assert removed is True
        assert still_in is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_entry_idempotent(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            removed = await repo.remove(duel_id=9999)
        assert removed is False


class TestIsInLobby:
    @pytest.mark.asyncio
    async def test_present_after_enqueue(self, uow: SqlAlchemyUnitOfWork) -> None:
        duel_id = await _seed_pending_duel(uow, tg_id=1)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            await repo.enqueue(duel_id=duel_id, enqueued_at=NOW)
            present = await repo.is_in_lobby(duel_id=duel_id)
        assert present is True

    @pytest.mark.asyncio
    async def test_absent_when_not_enqueued(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            present = await repo.is_in_lobby(duel_id=9999)
        assert present is False


class TestEnqueueDifferentDuels:
    """В лобби могут одновременно стоять разные дуэли."""

    @pytest.mark.asyncio
    async def test_enqueue_independent_duels(self, uow: SqlAlchemyUnitOfWork) -> None:
        d1 = await _seed_pending_duel(uow, tg_id=1)
        d2 = await _seed_pending_duel(uow, tg_id=2)
        repo = SqlAlchemyGlobalLobbyRepository(uow=uow)
        async with uow:
            ok1 = await repo.enqueue(duel_id=d1, enqueued_at=NOW)
            ok2 = await repo.enqueue(duel_id=d2, enqueued_at=NOW + timedelta(seconds=1))
            both_present = await repo.is_in_lobby(duel_id=d1) and await repo.is_in_lobby(duel_id=d2)
        assert ok1 is True
        assert ok2 is True
        assert both_present is True
