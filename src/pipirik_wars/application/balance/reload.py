"""Use-case `ReloadBalance` (Спринт 1.1.8 → 2.5-D.7, ГДД §2.3 / §18.6).

Перечитывает `config/balance.yaml` без рестарта бота. Доступ — через
RBAC-матрицу `IAdminAuthorizationPolicy.is_authorized(admin,
AdminCommandKind.RELOAD_BALANCE)` (по умолчанию — `super_admin` и
`economist`, см. `RoleBasedAdminAuthorizationPolicy`).

Acceptance из Спринта 1.1.8:
> Изменение YAML → `DisplayName` для тех же длин меняется; тест с
> двумя версиями таблицы.

Реализация:

1. `IAdminRepository.get_by_tg_id(...)` — load + проверка `is_active`.
2. `ensure_admin_authorized(...)` (Спринт 2.5-D.8) — проверка RBAC;
   при отказе пишет `ADMIN_AUTHORIZATION_DENIED` в admin-audit-логе
   и поднимает `AdminAuthorizationDeniedError`.
3. `IBalanceConfig.get()` — снимок до reload-а (нужен для `before` в аудите).
4. `IBalanceReloader.reload()` — собственно hot-reload (атомарный, в
   случае невалидного нового файла — старый снимок остаётся).
5. `IAuditLogger` + `IUnitOfWork` — атомарная запись в системный
   `audit_log` (`BALANCE_RELOAD`) с `before`/`after`.

Сам `reload()` не транзакционен (это in-memory-операция); системная
аудит-запись пишется **после** успешного reload в отдельной короткой
транзакции. При неуспехе `reload()` мы системный аудит не пишем —
состояние бота не изменилось.
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
from pipirik_wars.domain.balance import IBalanceConfig, IBalanceReloader
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class ReloadBalanceResult:
    """Что получилось.

    `version_before` / `version_after` — поле `version` балансовой
    конфигурации до и после reload-а. Равные значения — валидный
    сценарий («файл не меняли, но reload прошёл»).
    """

    version_before: int
    version_after: int


class ReloadBalance:
    """Use-case hot-reload-а балансовой конфигурации (admin-only)."""

    __slots__ = (
        "_admin_audit",
        "_admins",
        "_audit",
        "_authz",
        "_balance",
        "_clock",
        "_reloader",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        balance: IBalanceConfig,
        reloader: IBalanceReloader,
        audit: IAuditLogger,
        admin_audit: IAdminAuditLogger,
        authz: IAdminAuthorizationPolicy,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._balance = balance
        self._reloader = reloader
        self._audit = audit
        self._admin_audit = admin_audit
        self._authz = authz
        self._clock = clock

    async def execute(self, *, actor_tg_id: int) -> ReloadBalanceResult:
        """Выполнить hot-reload `balance.yaml`.

        Шаги:

        1. Загрузить `Admin` по `actor_tg_id`. Если такого нет / не
           активен — `AuthorizationError` (defense-in-depth, чтобы
           inactive-admin не могли вообще пройти RBAC-проверку).
        2. Вызвать `ensure_admin_authorized(...)` с `RELOAD_BALANCE` —
           при отказе helper сам пишет `ADMIN_AUTHORIZATION_DENIED` в
           admin-audit-логе (отдельная UoW-транзакция) и поднимает
           `AdminAuthorizationDeniedError`.
        3. Зафиксировать `version_before` через read-порт.
        4. Вызвать `reloader.reload()`. При ошибке — пробрасываем
           `ConfigError` дальше; системный аудит не пишем (нет state change).
        5. Записать `BALANCE_RELOAD` в системный `audit_log` внутри
           короткой UoW-транзакции.
        """
        admin = await self._admins.get_by_tg_id(actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_balance_write",
                detail=f"actor tg_id={actor_tg_id} is not an active admin",
            )

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.RELOAD_BALANCE,
            policy=self._authz,
            audit=self._admin_audit,
            uow=self._uow,
            target_kind="balance",
            target_id="balance.yaml",
            tg_chat_id=None,
            occurred_at=now,
        )

        version_before = self._balance.get().version
        new_snapshot = self._reloader.reload()
        version_after = new_snapshot.version

        async with self._uow:
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BALANCE_RELOAD,
                    actor_id=admin.id,
                    target_kind="balance",
                    target_id="balance.yaml",
                    before={"version": version_before},
                    after={"version": version_after},
                    reason="admin_balance_reload",
                    idempotency_key=(f"balance_reload:{actor_tg_id}:{int(now.timestamp())}"),
                    occurred_at=now,
                )
            )

        return ReloadBalanceResult(
            version_before=version_before,
            version_after=version_after,
        )
