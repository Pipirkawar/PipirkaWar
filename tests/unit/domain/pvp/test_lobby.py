"""Тесты VO `LobbyEntry` и контракта `IGlobalLobbyRepository` (Спринт 2.1.F).

`LobbyEntry` — frozen+slots, никаких мутаций. Контракт репо проверяется
через `FakeGlobalLobbyRepository` (поведение SqlAlchemy-реализации
зеркалит in-memory fake — отдельный integration-тест в
`tests/integration/db/test_global_lobby_repo.py`).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.pvp import LobbyEntry
from tests.fakes import FakeGlobalLobbyRepository

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
_T1 = _NOW + timedelta(seconds=1)
_T2 = _NOW + timedelta(seconds=2)


class TestLobbyEntry:
    def test_frozen(self) -> None:
        entry = LobbyEntry(duel_id=42, enqueued_at=_NOW)
        with pytest.raises(FrozenInstanceError):
            entry.duel_id = 99

    def test_equality_by_value(self) -> None:
        a = LobbyEntry(duel_id=42, enqueued_at=_NOW)
        b = LobbyEntry(duel_id=42, enqueued_at=_NOW)
        c = LobbyEntry(duel_id=43, enqueued_at=_NOW)
        assert a == b
        assert a != c


class TestFakeGlobalLobbyRepoContract:
    """Контракт `IGlobalLobbyRepository` через in-memory fake."""

    @pytest.mark.asyncio
    async def test_enqueue_appends_entry(self) -> None:
        repo = FakeGlobalLobbyRepository()
        ok = await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        assert ok is True
        assert await repo.is_in_lobby(duel_id=42) is True

    @pytest.mark.asyncio
    async def test_enqueue_idempotent_keeps_first_timestamp(self) -> None:
        repo = FakeGlobalLobbyRepository()
        first = await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        second = await repo.enqueue(duel_id=42, enqueued_at=_T2)
        assert first is True
        assert second is False
        # FIFO-инвариант — первоначальный момент сохраняется.
        popped = await repo.pop_oldest()
        assert popped is not None
        assert popped.duel_id == 42
        assert popped.enqueued_at == _NOW

    @pytest.mark.asyncio
    async def test_pop_oldest_returns_oldest_first(self) -> None:
        repo = FakeGlobalLobbyRepository()
        await repo.enqueue(duel_id=2, enqueued_at=_T1)
        await repo.enqueue(duel_id=1, enqueued_at=_NOW)
        await repo.enqueue(duel_id=3, enqueued_at=_T2)

        first = await repo.pop_oldest()
        second = await repo.pop_oldest()
        third = await repo.pop_oldest()
        assert first is not None and first.duel_id == 1
        assert second is not None and second.duel_id == 2
        assert third is not None and third.duel_id == 3
        assert await repo.pop_oldest() is None

    @pytest.mark.asyncio
    async def test_pop_oldest_empty_returns_none(self) -> None:
        repo = FakeGlobalLobbyRepository()
        assert await repo.pop_oldest() is None

    @pytest.mark.asyncio
    async def test_remove_existing(self) -> None:
        repo = FakeGlobalLobbyRepository()
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        removed = await repo.remove(duel_id=42)
        assert removed is True
        assert await repo.is_in_lobby(duel_id=42) is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_idempotent(self) -> None:
        repo = FakeGlobalLobbyRepository()
        removed = await repo.remove(duel_id=42)
        assert removed is False

    @pytest.mark.asyncio
    async def test_pop_oldest_removes_entry(self) -> None:
        repo = FakeGlobalLobbyRepository()
        await repo.enqueue(duel_id=42, enqueued_at=_NOW)
        await repo.pop_oldest()
        assert await repo.is_in_lobby(duel_id=42) is False
