"""Integration-тесты `SqlAlchemyActivityLockRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.security import LockReason
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyActivityLockRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class TestSqlAlchemyActivityLockRepository:
    @pytest.mark.asyncio
    async def test_first_acquire_succeeds(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        async with uow:
            ok = await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                now=now,
                expires_at=now + timedelta(minutes=2),
            )
        assert ok is True

    @pytest.mark.asyncio
    async def test_second_acquire_blocked(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        async with uow:
            await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                now=now,
                expires_at=now + timedelta(minutes=2),
            )
            ok2 = await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.ORACLE,
                now=now,
                expires_at=now + timedelta(minutes=2),
            )
        assert ok2 is False

    @pytest.mark.asyncio
    async def test_expired_lock_can_be_reacquired(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        t0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        async with uow:
            await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                now=t0,
                expires_at=t0 + timedelta(minutes=1),
            )

        # 5 минут спустя — старый блок истёк, должен переинсертиться.
        t1 = t0 + timedelta(minutes=5)
        async with uow:
            ok = await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.ORACLE,
                now=t1,
                expires_at=t1 + timedelta(minutes=1),
            )
        assert ok is True

        async with uow:
            lock = await repo.get(actor_kind="player", actor_id=1)
            assert lock is not None
            assert lock.reason is LockReason.ORACLE

    @pytest.mark.asyncio
    async def test_release_removes(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        t0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        async with uow:
            await repo.try_acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                now=t0,
                expires_at=t0 + timedelta(minutes=1),
            )
            await repo.release(actor_kind="player", actor_id=1)

        async with uow:
            lock = await repo.get(actor_kind="player", actor_id=1)
            assert lock is None

    @pytest.mark.asyncio
    async def test_release_nonexistent_is_noop(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        async with uow:
            await repo.release(actor_kind="player", actor_id=42)  # not there

    @pytest.mark.asyncio
    async def test_get_returns_none_when_absent(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyActivityLockRepository(uow=uow)
        async with uow:
            assert await repo.get(actor_kind="player", actor_id=999) is None
