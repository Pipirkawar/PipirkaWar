"""Integration-тесты `SqlAlchemyAdminRepository`."""

from __future__ import annotations

import pytest
from sqlalchemy import update

from pipirik_wars.domain.admin import AdminRole
from pipirik_wars.infrastructure.db.models import AdminORM
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

    @pytest.mark.asyncio
    async def test_totp_secret_defaults_to_none(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`add()` создаёт админа без 2FA — `totp_secret IS NULL`."""
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            admin = await repo.add(
                tg_id=7777,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note=None,
            )
            assert admin.totp_secret is None

        async with uow:
            found = await repo.get_by_tg_id(7777)
            assert found is not None
            assert found.totp_secret is None

    @pytest.mark.asyncio
    async def test_totp_secret_round_trips(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Если в БД лежит `totp_secret`, он маппится в `Admin.totp_secret`."""
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            await repo.add(
                tg_id=8888,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note=None,
            )
            # Явный UPDATE через ORM — реальный setup-команды для TOTP
            # появится в Спринте 2.5-D (`/admin_setup_totp`); сейчас
            # имитируем «secret уже выставлен».
            await uow.session.execute(
                update(AdminORM)
                .where(AdminORM.tg_id == 8888)
                .values(totp_secret="JBSWY3DPEHPK3PXP"),
            )

        async with uow:
            found = await repo.get_by_tg_id(8888)
            assert found is not None
            assert found.totp_secret == "JBSWY3DPEHPK3PXP"

    @pytest.mark.asyncio
    async def test_set_totp_secret_persists_after_commit(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`set_totp_secret(...)` атомарно пишет секрет; после коммита
        отдельная транзакция видит его через `get_by_tg_id`."""
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            admin = await repo.add(
                tg_id=11111,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note=None,
            )
            assert admin.id is not None
            assert admin.totp_secret is None
            admin_id = admin.id

        async with uow:
            await repo.set_totp_secret(
                admin_id=admin_id,
                secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
            )

        # Отдельный with-блок — гарантирует, что значение пережило commit
        # и не висит только в session-cache-е первой транзакции.
        async with uow:
            found = await repo.get_by_tg_id(11111)
            assert found is not None
            assert found.totp_secret == "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
            # Остальные поля не пострадали от UPDATE.
            assert found.role is AdminRole.SUPER_ADMIN
            assert found.is_active is True

    @pytest.mark.asyncio
    async def test_set_totp_secret_overwrites_existing_value(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """SQL-уровень не защищает от перезаписи (это ответственность use-case-а):
        повторный `set_totp_secret(...)` переписывает значение без ошибок.
        Гарантия «не переписывать» лежит в `SetupAdminTotp` (тест на это —
        в unit-suite-е use-case-а)."""
        repo = SqlAlchemyAdminRepository(uow=uow)
        async with uow:
            admin = await repo.add(
                tg_id=22222,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note=None,
            )
            assert admin.id is not None
            admin_id = admin.id

        async with uow:
            await repo.set_totp_secret(admin_id=admin_id, secret="OLDSECRET234567")

        async with uow:
            await repo.set_totp_secret(admin_id=admin_id, secret="NEWSECRET234567")

        async with uow:
            found = await repo.get_by_tg_id(22222)
            assert found is not None
            assert found.totp_secret == "NEWSECRET234567"

    @pytest.mark.asyncio
    async def test_set_totp_secret_unknown_admin_raises_concurrency_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Если админ удалён/не существует — UPDATE даёт `rowcount=0`,
        и репо поднимает `ConcurrencyError` (use-case откатывает свою UoW)."""
        repo = SqlAlchemyAdminRepository(uow=uow)
        with pytest.raises(ConcurrencyError, match="not found for set_totp_secret"):
            async with uow:
                await repo.set_totp_secret(admin_id=999_999, secret="ANYSECRET234567")
