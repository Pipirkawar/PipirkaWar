"""Unit-тесты `ActivityLockService` на fake-репозитории."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.security import (
    ActivityLock,
    IActivityLockRepository,
    LockAlreadyHeldError,
    LockReason,
)
from tests.fakes import FakeClock


@dataclass
class FakeLockRepo(IActivityLockRepository):
    """In-memory fake. PK = (actor_kind, actor_id)."""

    locks: dict[tuple[str, int], ActivityLock] = field(default_factory=dict)

    async def try_acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        key = (actor_kind, actor_id)
        existing = self.locks.get(key)
        if existing is not None and not existing.is_expired(now=now):
            return False
        self.locks[key] = ActivityLock(
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=reason,
            acquired_at=now,
            expires_at=expires_at,
        )
        return True

    async def release(self, *, actor_kind: str, actor_id: int) -> None:
        self.locks.pop((actor_kind, actor_id), None)

    async def get(self, *, actor_kind: str, actor_id: int) -> ActivityLock | None:
        return self.locks.get((actor_kind, actor_id))


class TestActivityLockService:
    @pytest.mark.asyncio
    async def test_acquire_first_time_succeeds(self) -> None:
        repo = FakeLockRepo()
        svc = ActivityLockService(repository=repo, clock=FakeClock())

        await svc.acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            ttl=timedelta(minutes=2),
        )

        lock = await repo.get(actor_kind="player", actor_id=42)
        assert lock is not None
        assert lock.reason is LockReason.FOREST

    @pytest.mark.asyncio
    async def test_double_acquire_raises_lock_already_held(self) -> None:
        repo = FakeLockRepo()
        svc = ActivityLockService(repository=repo, clock=FakeClock())

        await svc.acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            ttl=timedelta(minutes=2),
        )
        with pytest.raises(LockAlreadyHeldError) as exc:
            await svc.acquire(
                actor_kind="player",
                actor_id=42,
                reason=LockReason.ORACLE,
                ttl=timedelta(minutes=2),
            )
        assert exc.value.actor_kind == "player"
        assert exc.value.actor_id == 42

    @pytest.mark.asyncio
    async def test_expired_lock_is_overwritten(self) -> None:
        clock = FakeClock()
        repo = FakeLockRepo()
        svc = ActivityLockService(repository=repo, clock=clock)

        await svc.acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            ttl=timedelta(seconds=1),
        )
        clock.advance(minutes=5)
        # Истёк — повторный захват должен пройти.
        await svc.acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.ORACLE,
            ttl=timedelta(minutes=2),
        )
        lock = await repo.get(actor_kind="player", actor_id=42)
        assert lock is not None
        assert lock.reason is LockReason.ORACLE

    @pytest.mark.asyncio
    async def test_release_removes_lock(self) -> None:
        repo = FakeLockRepo()
        svc = ActivityLockService(repository=repo, clock=FakeClock())

        await svc.acquire(
            actor_kind="player",
            actor_id=42,
            reason=LockReason.FOREST,
            ttl=timedelta(minutes=2),
        )
        await svc.release(actor_kind="player", actor_id=42)

        assert await repo.get(actor_kind="player", actor_id=42) is None

    @pytest.mark.asyncio
    async def test_release_nonexistent_is_noop(self) -> None:
        repo = FakeLockRepo()
        svc = ActivityLockService(repository=repo, clock=FakeClock())

        await svc.release(actor_kind="player", actor_id=999)  # не падает

    @pytest.mark.asyncio
    async def test_acquire_zero_ttl_raises(self) -> None:
        svc = ActivityLockService(repository=FakeLockRepo(), clock=FakeClock())
        with pytest.raises(ValueError, match="ttl must be positive"):
            await svc.acquire(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                ttl=timedelta(seconds=0),
            )
