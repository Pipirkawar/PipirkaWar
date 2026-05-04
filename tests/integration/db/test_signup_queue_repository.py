"""Integration-тесты `SqlAlchemySignupQueueRepository` (Спринт 1.2.4).

Гоняем на in-memory SQLite через тот же `Base.metadata` —
так же, как остальные `tests/integration/db/*`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    SignupQueueEntry,
)
from pipirik_wars.infrastructure.db.repositories import SqlAlchemySignupQueueRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

_BASE_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def _entry(*, tg_id: int, offset_seconds: int = 0) -> SignupQueueEntry:
    return SignupQueueEntry(
        id=None,
        tg_id=tg_id,
        username=f"u{tg_id}",
        locale="ru",
        position=0,
        enqueued_at=_BASE_NOW + timedelta(seconds=offset_seconds),
    )


class TestSqlAlchemySignupQueueRepository:
    @pytest.mark.asyncio
    async def test_enqueue_assigns_id_and_position_one(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            saved = await repo.enqueue(entry=_entry(tg_id=101))

        assert saved.id is not None
        assert saved.tg_id == 101
        assert saved.username == "u101"
        assert saved.locale == "ru"
        assert saved.position == 1

    @pytest.mark.asyncio
    async def test_enqueue_assigns_increasing_positions(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            first = await repo.enqueue(entry=_entry(tg_id=201, offset_seconds=0))
            second = await repo.enqueue(entry=_entry(tg_id=202, offset_seconds=1))
            third = await repo.enqueue(entry=_entry(tg_id=203, offset_seconds=2))

        assert first.position == 1
        assert second.position == 2
        assert third.position == 3

    @pytest.mark.asyncio
    async def test_duplicate_tg_id_raises_already_queued(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=42))

        with pytest.raises(AlreadyQueuedError) as exc_info:
            async with uow:
                await repo.enqueue(entry=_entry(tg_id=42))
        assert exc_info.value.tg_id == 42

    @pytest.mark.asyncio
    async def test_enqueue_rejects_pre_set_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        bad = SignupQueueEntry(
            id=999,
            tg_id=42,
            username=None,
            locale=None,
            position=0,
            enqueued_at=_BASE_NOW,
        )
        with pytest.raises(ValueError, match="pre-set id"):
            async with uow:
                await repo.enqueue(entry=bad)

    @pytest.mark.asyncio
    async def test_get_by_tg_id_returns_entry_with_actual_position(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=301, offset_seconds=0))
            await repo.enqueue(entry=_entry(tg_id=302, offset_seconds=1))
            await repo.enqueue(entry=_entry(tg_id=303, offset_seconds=2))

        async with uow:
            second = await repo.get_by_tg_id(302)
            missing = await repo.get_by_tg_id(404)

        assert second is not None
        assert second.position == 2
        assert second.tg_id == 302
        assert missing is None

    @pytest.mark.asyncio
    async def test_size_grows_with_enqueue(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            assert await repo.size() == 0
            await repo.enqueue(entry=_entry(tg_id=401))
            assert await repo.size() == 1
            await repo.enqueue(entry=_entry(tg_id=402, offset_seconds=1))
            assert await repo.size() == 2

    @pytest.mark.asyncio
    async def test_pop_front_zero_limit_does_not_change_state(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=501))
            popped_zero = await repo.pop_front(limit=0)
            popped_neg = await repo.pop_front(limit=-5)

        assert popped_zero == []
        assert popped_neg == []
        async with uow:
            assert await repo.size() == 1

    @pytest.mark.asyncio
    async def test_pop_front_returns_in_fifo_order(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=601, offset_seconds=0))
            await repo.enqueue(entry=_entry(tg_id=602, offset_seconds=1))
            await repo.enqueue(entry=_entry(tg_id=603, offset_seconds=2))

        async with uow:
            popped = await repo.pop_front(limit=2)

        assert [entry.tg_id for entry in popped] == [601, 602]
        assert [entry.position for entry in popped] == [1, 2]
        async with uow:
            assert await repo.size() == 1
            remaining = await repo.get_by_tg_id(603)
        assert remaining is not None
        # После pop_front оставшийся стал первым.
        assert remaining.position == 1

    @pytest.mark.asyncio
    async def test_pop_front_more_than_size_returns_all(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=701, offset_seconds=0))
            await repo.enqueue(entry=_entry(tg_id=702, offset_seconds=1))

        async with uow:
            popped = await repo.pop_front(limit=10)

        assert [entry.tg_id for entry in popped] == [701, 702]
        async with uow:
            assert await repo.size() == 0

    @pytest.mark.asyncio
    async def test_re_enqueue_after_pop_front_succeeds(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        async with uow:
            await repo.enqueue(entry=_entry(tg_id=801))

        async with uow:
            await repo.pop_front(limit=1)

        async with uow:
            again = await repo.enqueue(
                entry=_entry(tg_id=801, offset_seconds=10),
            )

        assert again.id is not None
        assert again.position == 1

    @pytest.mark.asyncio
    async def test_position_breaks_ties_by_tg_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """При одинаковом `enqueued_at` позиция упорядочивается по `tg_id`."""
        repo = SqlAlchemySignupQueueRepository(uow=uow)
        same_time = _BASE_NOW
        async with uow:
            await repo.enqueue(
                entry=SignupQueueEntry(
                    id=None,
                    tg_id=999,
                    username=None,
                    locale=None,
                    position=0,
                    enqueued_at=same_time,
                ),
            )
            await repo.enqueue(
                entry=SignupQueueEntry(
                    id=None,
                    tg_id=100,
                    username=None,
                    locale=None,
                    position=0,
                    enqueued_at=same_time,
                ),
            )

        # Сверяем «текущие» позиции через get_by_tg_id — меньший tg_id впереди.
        async with uow:
            small = await repo.get_by_tg_id(100)
            big = await repo.get_by_tg_id(999)

        assert small is not None
        assert big is not None
        assert small.position == 1
        assert big.position == 2
