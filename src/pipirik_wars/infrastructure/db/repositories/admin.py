"""Реализация `IAdminRepository` поверх таблицы `admins`."""

from __future__ import annotations

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.admin import Admin, AdminRole, IAdminRepository
from pipirik_wars.infrastructure.db.models import AdminORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import ConcurrencyError


def _row_to_entity(row: AdminORM) -> Admin:
    return Admin(
        id=row.id,
        tg_id=row.tg_id,
        role=AdminRole(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
        created_by_admin_id=row.created_by_admin_id,
        note=row.note,
        totp_secret=row.totp_secret,
    )


class SqlAlchemyAdminRepository(IAdminRepository):
    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def count_active(self) -> int:
        result = await self._uow.session.execute(
            select(func.count(AdminORM.id)).where(AdminORM.is_active.is_(True)),
        )
        value = result.scalar_one()
        return int(value)

    async def get_by_tg_id(self, tg_id: int) -> Admin | None:
        result = await self._uow.session.execute(
            select(AdminORM).where(AdminORM.tg_id == tg_id),
        )
        row = result.scalar_one_or_none()
        return _row_to_entity(row) if row is not None else None

    async def add(
        self,
        *,
        tg_id: int,
        role: AdminRole,
        created_by_admin_id: int | None,
        note: str | None,
    ) -> Admin:
        row = AdminORM(
            tg_id=tg_id,
            role=role.value,
            is_active=True,
            created_by_admin_id=created_by_admin_id,
            note=note,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except IntegrityError as exc:
            raise ConcurrencyError(f"admin tg_id={tg_id} already exists") from exc
        return _row_to_entity(row)

    async def set_totp_secret(self, *, admin_id: int, secret: str) -> None:
        # Один атомарный UPDATE — без предварительного SELECT-а: проверка
        # `admin.totp_secret is None` уже сделана на слое use-case-а
        # (`SetupAdminTotp` бросит `TotpAlreadyConfiguredError` до сюда),
        # а здесь нам нужно только записать. Если конкурентно админ был
        # удалён/переместился — `rowcount == 0`, поднимаем `ConcurrencyError`.
        result = await self._uow.session.execute(
            update(AdminORM).where(AdminORM.id == admin_id).values(totp_secret=secret),
        )
        # UPDATE возвращает CursorResult; защищаемся от изменений API
        # (та же страховка, что в `SqlAlchemyClanMembershipRepository.remove`).
        if not isinstance(result, CursorResult):  # pragma: no cover
            raise RuntimeError("UPDATE must return CursorResult")
        if not (result.rowcount and result.rowcount > 0):
            raise ConcurrencyError(f"admin id={admin_id} not found for set_totp_secret")
