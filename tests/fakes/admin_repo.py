"""In-memory реализация `IAdminRepository`.

Соответствует поведению SQLAlchemy-реализации:
- `add(...)` бросает `ConcurrencyError` при дубле `tg_id`;
- `count_active()` считает только `is_active=True` записи.

Используется в unit-тестах application-слоя (Спринт 1.1.E:
`ReloadBalance` авторизация и аналогичные admin-команды).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from pipirik_wars.domain.admin import Admin, AdminRole, IAdminRepository
from pipirik_wars.shared.errors import ConcurrencyError


@dataclass
class FakeAdminRepository(IAdminRepository):
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
            raise ConcurrencyError(f"admin tg_id={tg_id} already exists")
        new_id = (max((a.id or 0 for a in self.rows), default=0)) + 1
        admin = Admin(
            id=new_id,
            tg_id=tg_id,
            role=role,
            is_active=True,
            created_at=datetime.now(UTC),
            created_by_admin_id=created_by_admin_id,
            note=note,
        )
        self.rows.append(admin)
        return admin

    def seed(
        self,
        *,
        tg_id: int,
        role: AdminRole,
        is_active: bool = True,
        admin_id: int | None = None,
    ) -> Admin:
        """Подложить админа без вызова бизнес-логики (для arrange-секции)."""
        new_id = admin_id or (max((a.id or 0 for a in self.rows), default=0) + 1)
        admin = Admin(
            id=new_id,
            tg_id=tg_id,
            role=role,
            is_active=is_active,
            created_at=datetime.now(UTC),
            created_by_admin_id=None,
            note=None,
        )
        self.rows.append(admin)
        return admin

    def deactivate(self, *, tg_id: int) -> None:
        """Помечает существующего админа как неактивного (для тестов RBAC)."""
        for i, a in enumerate(self.rows):
            if a.tg_id == tg_id:
                self.rows[i] = replace(a, is_active=False)
                return
