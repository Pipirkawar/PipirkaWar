"""Unit-тесты `InMemoryAdminConfirmStore` (Спринт 2.5-A.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.admin import AdminConfirmEntry, AdminConfirmRequest
from pipirik_wars.infrastructure.admin.in_memory_confirm_store import (
    InMemoryAdminConfirmStore,
)


def _entry(*, admin_id: int = 1, expires_at: datetime | None = None) -> AdminConfirmEntry:
    return AdminConfirmEntry(
        request=AdminConfirmRequest(
            admin_id=admin_id,
            command_kind="ban",
            target_kind="player",
            target_id="42",
        ),
        expires_at=expires_at or datetime(2026, 5, 7, 12, 1, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
class TestInMemoryAdminConfirmStore:
    async def test_save_then_pop_returns_entry(self) -> None:
        store = InMemoryAdminConfirmStore()
        entry = _entry()

        await store.save(token="tok", entry=entry)
        result = await store.pop(token="tok")

        assert result is entry

    async def test_pop_is_one_shot(self) -> None:
        store = InMemoryAdminConfirmStore()
        await store.save(token="tok", entry=_entry())
        first = await store.pop(token="tok")
        second = await store.pop(token="tok")

        assert first is not None
        assert second is None

    async def test_pop_unknown_returns_none(self) -> None:
        store = InMemoryAdminConfirmStore()
        assert await store.pop(token="nope") is None

    async def test_save_overwrites_same_token(self) -> None:
        """Маловероятная коллизия токенов не должна ломать поведение."""
        store = InMemoryAdminConfirmStore()
        await store.save(token="tok", entry=_entry(admin_id=1))
        await store.save(token="tok", entry=_entry(admin_id=2))
        result = await store.pop(token="tok")

        assert result is not None
        assert result.request.admin_id == 2

    async def test_cleanup_expired_drops_only_expired(self) -> None:
        store = InMemoryAdminConfirmStore()
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
        await store.save(
            token="alive",
            entry=_entry(expires_at=now + timedelta(seconds=10)),
        )
        await store.save(
            token="expired",
            entry=_entry(expires_at=now - timedelta(seconds=1)),
        )

        removed = await store.cleanup_expired(now=now)

        assert removed == 1
        assert await store.pop(token="expired") is None
        assert await store.pop(token="alive") is not None

    async def test_cleanup_returns_zero_when_nothing_expired(self) -> None:
        store = InMemoryAdminConfirmStore()
        now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
        await store.save(
            token="alive",
            entry=_entry(expires_at=now + timedelta(seconds=10)),
        )
        assert await store.cleanup_expired(now=now) == 0
