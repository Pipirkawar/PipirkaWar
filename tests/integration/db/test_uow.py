"""Integration-тесты `SqlAlchemyUnitOfWork`."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from pipirik_wars.infrastructure.db.models import IdempotencyKeyORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class TestSqlAlchemyUnitOfWork:
    @pytest.mark.asyncio
    async def test_commit_on_clean_exit(self, uow: SqlAlchemyUnitOfWork) -> None:
        async with uow:
            uow.session.add(
                IdempotencyKeyORM(key="forest:1", namespace="forest"),
            )

        async with uow:
            res = await uow.session.execute(
                select(IdempotencyKeyORM.key).where(IdempotencyKeyORM.key == "forest:1"),
            )
            assert res.scalar_one_or_none() == "forest:1"

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self, uow: SqlAlchemyUnitOfWork) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with uow:
                uow.session.add(
                    IdempotencyKeyORM(key="rollback:1", namespace="forest"),
                )
                raise RuntimeError("boom")

        async with uow:
            res = await uow.session.execute(
                select(IdempotencyKeyORM.key).where(IdempotencyKeyORM.key == "rollback:1"),
            )
            assert res.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_session_unavailable_outside_context(self, uow: SqlAlchemyUnitOfWork) -> None:
        with pytest.raises(RuntimeError, match="not entered"):
            _ = uow.session

    @pytest.mark.asyncio
    async def test_nested_context_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        async with uow:
            with pytest.raises(RuntimeError, match="Nested"):
                async with uow:
                    pass

    @pytest.mark.asyncio
    async def test_commit_method_inside_context(self, uow: SqlAlchemyUnitOfWork) -> None:
        async with uow:
            uow.session.add(
                IdempotencyKeyORM(key="mid:1", namespace="forest"),
            )
            await uow.commit()
            # Запись осталась после commit, sessions reused.
            res = await uow.session.execute(
                select(IdempotencyKeyORM.key),
            )
            keys = [r[0] for r in res.all()]
            assert "mid:1" in keys

    @pytest.mark.asyncio
    async def test_explicit_rollback_inside_context(self, uow: SqlAlchemyUnitOfWork) -> None:
        async with uow:
            uow.session.add(
                IdempotencyKeyORM(key="rb:1", namespace="forest"),
            )
            await uow.rollback()

        async with uow:
            res = await uow.session.execute(
                select(IdempotencyKeyORM.key).where(IdempotencyKeyORM.key == "rb:1"),
            )
            assert res.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_commit_outside_context_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        with pytest.raises(RuntimeError, match="not entered"):
            await uow.commit()

    @pytest.mark.asyncio
    async def test_rollback_outside_context_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        with pytest.raises(RuntimeError, match="not entered"):
            await uow.rollback()
