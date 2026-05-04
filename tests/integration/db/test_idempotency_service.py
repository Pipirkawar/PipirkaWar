"""Integration-тесты `SqlAlchemyIdempotencyService`."""

from __future__ import annotations

import pytest

from pipirik_wars.infrastructure.db.services import SqlAlchemyIdempotencyService
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class TestSqlAlchemyIdempotencyService:
    @pytest.mark.asyncio
    async def test_build_key(self, uow: SqlAlchemyUnitOfWork) -> None:
        svc = SqlAlchemyIdempotencyService(uow=uow)
        key = svc.build("forest", ["player:1", "2026-05-04"])
        assert key == "forest:player:1|2026-05-04"

    @pytest.mark.asyncio
    async def test_build_empty_namespace_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        svc = SqlAlchemyIdempotencyService(uow=uow)
        with pytest.raises(ValueError):
            svc.build("", ["x"])

    @pytest.mark.asyncio
    async def test_mark_then_is_seen(self, uow: SqlAlchemyUnitOfWork) -> None:
        svc = SqlAlchemyIdempotencyService(uow=uow)
        async with uow:
            assert await svc.is_seen("forest:1") is False
            await svc.mark("forest:1", namespace="forest")

        async with uow:
            assert await svc.is_seen("forest:1") is True

    @pytest.mark.asyncio
    async def test_mark_twice_is_noop(self, uow: SqlAlchemyUnitOfWork) -> None:
        svc = SqlAlchemyIdempotencyService(uow=uow)
        async with uow:
            await svc.mark("forest:dup", namespace="forest")
            await svc.mark("forest:dup", namespace="forest")  # ON CONFLICT DO NOTHING

        async with uow:
            assert await svc.is_seen("forest:dup") is True

    @pytest.mark.asyncio
    async def test_mark_namespace_mismatch_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        svc = SqlAlchemyIdempotencyService(uow=uow)
        async with uow:
            with pytest.raises(ValueError, match="does not match namespace"):
                await svc.mark("forest:abc", namespace="oracle")
