"""Unit-тесты `BootstrapSuperAdmin`.

Проверяем:
1. Идемпотентность: при непустой `admins` — NO-OP.
2. При пустой `admins` — добавляются только переданные `tg_id`-ы.
3. Audit-лог содержит запись на каждое добавление.
4. Дубли в списке — игнорируются (uniq, сохранение порядка).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from pipirik_wars.application.bootstrap import BootstrapSuperAdmin
from pipirik_wars.domain.admin import Admin, AdminRole, IAdminRepository
from pipirik_wars.shared.errors import ConcurrencyError
from tests.fakes import FakeAuditLogger, FakeClock


@dataclass
class FakeAdminRepo(IAdminRepository):
    rows: list[Admin] = field(default_factory=list)

    async def count_active(self) -> int:
        return sum(1 for a in self.rows if a.is_active)

    async def get_by_tg_id(self, tg_id: int) -> Admin | None:
        for a in self.rows:
            if a.tg_id == tg_id:
                return a
        return None

    async def add(
        self,
        *,
        tg_id: int,
        role: AdminRole,
        created_by_admin_id: int | None,
        note: str | None,
    ) -> Admin:
        if any(a.tg_id == tg_id for a in self.rows):
            raise ConcurrencyError(f"tg_id {tg_id} exists")
        admin = Admin(
            id=len(self.rows) + 1,
            tg_id=tg_id,
            role=role,
            is_active=True,
            created_at=datetime(2026, 5, 4),
            created_by_admin_id=created_by_admin_id,
            note=note,
        )
        self.rows.append(admin)
        return admin


class TestBootstrapSuperAdmin:
    @pytest.mark.asyncio
    async def test_grants_when_table_empty(self) -> None:
        repo = FakeAdminRepo()
        audit = FakeAuditLogger()
        bootstrap = BootstrapSuperAdmin(admins=repo, audit=audit, clock=FakeClock())

        result = await bootstrap.execute(tg_ids=[111, 222])

        assert result.skipped_reason is None
        assert result.granted_tg_ids == (111, 222)
        assert len(repo.rows) == 2
        assert {a.role for a in repo.rows} == {AdminRole.SUPER_ADMIN}
        assert len(audit.entries) == 2

    @pytest.mark.asyncio
    async def test_skipped_when_admins_present(self) -> None:
        repo = FakeAdminRepo(
            rows=[
                Admin(
                    id=1,
                    tg_id=999,
                    role=AdminRole.SUPER_ADMIN,
                    is_active=True,
                    created_at=datetime(2026, 1, 1),
                ),
            ],
        )
        bootstrap = BootstrapSuperAdmin(admins=repo, audit=FakeAuditLogger(), clock=FakeClock())
        result = await bootstrap.execute(tg_ids=[111, 222])

        assert result.skipped_reason == "admins_table_not_empty"
        assert result.granted_tg_ids == ()
        assert len(repo.rows) == 1  # ничего не добавилось

    @pytest.mark.asyncio
    async def test_skipped_when_no_ids(self) -> None:
        repo = FakeAdminRepo()
        bootstrap = BootstrapSuperAdmin(admins=repo, audit=FakeAuditLogger(), clock=FakeClock())
        result = await bootstrap.execute(tg_ids=[])
        assert result.skipped_reason == "no_ids_provided"
        assert result.granted_tg_ids == ()

    @pytest.mark.asyncio
    async def test_dedupes_input_ids(self) -> None:
        repo = FakeAdminRepo()
        bootstrap = BootstrapSuperAdmin(admins=repo, audit=FakeAuditLogger(), clock=FakeClock())
        result = await bootstrap.execute(tg_ids=[111, 222, 111, 222])
        assert result.granted_tg_ids == (111, 222)
        assert len(repo.rows) == 2

    @pytest.mark.asyncio
    async def test_inactive_admins_not_counted(self) -> None:
        """Если все админы деактивированы — bootstrap снова срабатывает."""
        repo = FakeAdminRepo(
            rows=[
                Admin(
                    id=1,
                    tg_id=999,
                    role=AdminRole.SUPER_ADMIN,
                    is_active=False,
                    created_at=datetime(2026, 1, 1),
                ),
            ],
        )
        bootstrap = BootstrapSuperAdmin(admins=repo, audit=FakeAuditLogger(), clock=FakeClock())
        result = await bootstrap.execute(tg_ids=[42])
        assert result.skipped_reason is None
        assert result.granted_tg_ids == (42,)
