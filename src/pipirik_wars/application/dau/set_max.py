"""Use-case `SetMaxDau` (Спринт 1.2.6 → 2.5-D.7, ГДД §18.4).

Меняет runtime-лимит `MAX_DAU` без рестарта бота. Доступ — через
RBAC-матрицу `IAdminAuthorizationPolicy.is_authorized(admin,
AdminCommandKind.SET_MAX_DAU)` (по умолчанию — только `super_admin`,
см. `RoleBasedAdminAuthorizationPolicy`).

Атомарность:

1. Загрузка `Admin` + проверка `is_active` → `AuthorizationError`.
2. `ensure_admin_authorized(...)` (Спринт 2.5-D.8) — RBAC; при отказе
   пишет `ADMIN_AUTHORIZATION_DENIED` в admin-audit-логе и поднимает
   `AdminAuthorizationDeniedError`.
3. Валидация `max_dau >= 1` → `ValueError` пробрасывается дальше.
4. `IDauLimit.set(...)` — in-memory, синхронный side-effect (хранится
   в одном поле int + asyncio.Lock).
5. Запись в системный `audit_log` (`DAU_LIMIT_CHANGE`) с `before`/`after`
   в отдельной короткой UoW-транзакции. Если запись падает — лимит уже
   изменён, но это приемлемо: in-memory state бота важнее, чем
   безупречный аудит. Альтернатива «откатить set при ошибке audit»
   создала бы гонку.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.dau import IDauLimit
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class SetMaxDauResult:
    """Результат `/set_max_dau`."""

    previous_max_dau: int
    new_max_dau: int

    @property
    def changed(self) -> bool:
        return self.previous_max_dau != self.new_max_dau


class SetMaxDau:
    """Use-case изменения `MAX_DAU` (admin-only)."""

    __slots__ = (
        "_admin_audit",
        "_admins",
        "_audit",
        "_authz",
        "_clock",
        "_limit",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        limit: IDauLimit,
        audit: IAuditLogger,
        admin_audit: IAdminAuditLogger,
        authz: IAdminAuthorizationPolicy,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._limit = limit
        self._audit = audit
        self._admin_audit = admin_audit
        self._authz = authz
        self._clock = clock

    async def execute(
        self,
        *,
        actor_tg_id: int,
        new_max_dau: int,
    ) -> SetMaxDauResult:
        """Установить новый `MAX_DAU`.

        Бросает:

        - `AuthorizationError` — если актор не админ или не активен.
        - `AdminAuthorizationDeniedError` — если RBAC-роль не покрывает
          `SET_MAX_DAU` (через `ensure_admin_authorized`).
        - `ValueError` — если `new_max_dau < 1`.
        """
        admin = await self._admins.get_by_tg_id(actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_runtime_config",
                detail=f"actor tg_id={actor_tg_id} is not an active admin",
            )

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.SET_MAX_DAU,
            policy=self._authz,
            audit=self._admin_audit,
            uow=self._uow,
            target_kind="dau_limit",
            target_id="MAX_DAU",
            tg_chat_id=None,
            occurred_at=now,
        )

        if new_max_dau < 1:
            raise ValueError(f"new_max_dau must be >= 1, got {new_max_dau}")

        previous = await self._limit.set(max_dau=new_max_dau)

        async with self._uow:
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.DAU_LIMIT_CHANGE,
                    actor_id=admin.id,
                    target_kind="dau_limit",
                    target_id="MAX_DAU",
                    before={"max_dau": previous},
                    after={"max_dau": new_max_dau},
                    reason="admin_set_max_dau",
                    idempotency_key=(f"set_max_dau:{actor_tg_id}:{int(now.timestamp())}"),
                    occurred_at=now,
                )
            )

        return SetMaxDauResult(
            previous_max_dau=previous,
            new_max_dau=new_max_dau,
        )
