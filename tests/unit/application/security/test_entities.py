"""Unit-тесты доменных сущностей подсистемы безопасности."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.security import ActivityLock, LockReason


class TestActivityLockNew:
    def test_new_sets_acquired_and_expires(self) -> None:
        now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        lock = ActivityLock.new(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.FOREST,
            now=now,
            ttl=timedelta(minutes=2),
        )
        assert lock.acquired_at == now
        assert lock.expires_at == now + timedelta(minutes=2)

    def test_new_zero_ttl_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ActivityLock.new(
                actor_kind="player",
                actor_id=1,
                reason=LockReason.FOREST,
                now=datetime(2026, 5, 4, tzinfo=UTC),
                ttl=timedelta(seconds=0),
            )

    def test_is_expired_true_after_ttl(self) -> None:
        now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
        lock = ActivityLock.new(
            actor_kind="player",
            actor_id=1,
            reason=LockReason.FOREST,
            now=now,
            ttl=timedelta(minutes=2),
        )
        assert not lock.is_expired(now=now)
        assert not lock.is_expired(now=now + timedelta(minutes=1))
        assert lock.is_expired(now=now + timedelta(minutes=2))
        assert lock.is_expired(now=now + timedelta(minutes=3))
