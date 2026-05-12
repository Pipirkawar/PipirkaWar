"""Integration-тесты ``SqlAlchemyPayoutFreezeRepository`` (Спринт 4.1-E, E.11a).

Покрытие:

* ``get_state()`` — default seed-row ``is_frozen=FALSE`` после
  ``create_all`` + conftest seed.
* ``set_frozen(admin_id, at, reason)`` — записывает frozen-состояние,
  ``get_state()`` после commit-а возвращает обновлённый снапшот.
* ``set_unfrozen()`` — сбрасывает состояние в ``is_frozen=FALSE``.
* Идемпотентность: повторный ``set_frozen`` / ``set_unfrozen`` —
  перезаписывает, не дублирует строку.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPayoutFreezeRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

_FREEZE_AT = datetime(2026, 5, 12, 14, 0, tzinfo=UTC)
_ADMIN_ID = 7
_REASON = "suspicious activity"


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyPayoutFreezeRepository:
    return SqlAlchemyPayoutFreezeRepository(uow=uow)


class TestGetState:
    @pytest.mark.asyncio
    async def test_default_is_unfrozen(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            state = await repo.get_state()
        assert state.is_frozen is False
        assert state.frozen_by_admin_id is None
        assert state.frozen_at is None
        assert state.reason is None


class TestSetFrozen:
    @pytest.mark.asyncio
    async def test_set_frozen_persists(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            result = await repo.set_frozen(
                admin_id=_ADMIN_ID,
                at=_FREEZE_AT,
                reason=_REASON,
            )
        assert result.is_frozen is True
        assert result.frozen_by_admin_id == _ADMIN_ID
        assert result.frozen_at == _FREEZE_AT
        assert result.reason == _REASON

        async with uow:
            reloaded = await repo.get_state()
        assert reloaded.is_frozen is True
        assert reloaded.frozen_by_admin_id == _ADMIN_ID

    @pytest.mark.asyncio
    async def test_set_frozen_idempotent(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            await repo.set_frozen(
                admin_id=_ADMIN_ID,
                at=_FREEZE_AT,
                reason=_REASON,
            )
        new_at = datetime(2026, 5, 12, 15, 0, tzinfo=UTC)
        async with uow:
            result = await repo.set_frozen(
                admin_id=_ADMIN_ID,
                at=new_at,
                reason="updated reason",
            )
        assert result.is_frozen is True
        assert result.frozen_at == new_at
        assert result.reason == "updated reason"


class TestSetUnfrozen:
    @pytest.mark.asyncio
    async def test_set_unfrozen_after_frozen(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            await repo.set_frozen(
                admin_id=_ADMIN_ID,
                at=_FREEZE_AT,
                reason=_REASON,
            )
        async with uow:
            result = await repo.set_unfrozen()
        assert result.is_frozen is False
        assert result.frozen_by_admin_id is None

        async with uow:
            reloaded = await repo.get_state()
        assert reloaded.is_frozen is False

    @pytest.mark.asyncio
    async def test_set_unfrozen_idempotent(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            result = await repo.set_unfrozen()
        assert result.is_frozen is False
        async with uow:
            result2 = await repo.set_unfrozen()
        assert result2.is_frozen is False
