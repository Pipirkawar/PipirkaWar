"""Integration-тесты `SqlAlchemyAdminRepository`."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.admin import AdminRole
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import ConcurrencyError


class TestSqlAlchemyAdminRepository:
    @pytest.mark.asyncio
    async def test_count_active_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            assert await repo.count_active() == 0

    @pytest.mark.asyncio
    async def test_add_then_count(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            admin = await repo.add(
                tg_id=12345,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note="bootstrap",
            )
            assert admin.id is not None
            assert admin.tg_id == 12345
            assert admin.role is AdminRole.SUPER_ADMIN
            assert admin.is_active is True

        async with uow:
            assert await repo.count_active() == 1

    @pytest.mark.asyncio
    async def test_get_by_tg_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            await repo.add(
                tg_id=999,
                role=AdminRole.ECONOMIST,
                created_by_admin_id=None,
                note=None,
            )

        async with uow:
            found = await repo.get_by_tg_id(999)
            assert found is not None
            assert found.role is AdminRole.ECONOMIST
            assert await repo.get_by_tg_id(404) is None

    @pytest.mark.asyncio
    async def test_duplicate_tg_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            await repo.add(
                tg_id=42,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note=None,
            )

        # Дубль во второй транзакции: with-блок вылетает с ConcurrencyError,
        # UoW сам откатывается через __aexit__.
        with pytest.raises(ConcurrencyError, match="already exists"):
            async with uow:
                await repo.add(
                    tg_id=42,
                    role=AdminRole.SUPPORT,
                    created_by_admin_id=None,
                    note="duplicate",
                )
