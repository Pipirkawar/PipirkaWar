"""Use-case `ReloadBalance` (Спринт 1.1.8, ГДД §2.3 / §18.6.5).

Перечитывает `config/balance.yaml` без рестарта бота. Доступен **только
активным админам с правом на запись балансовых констант**
(`super_admin` или `economist`, см. `Admin.can_write_balance()`).

Acceptance из Спринта 1.1.8:
> Изменение YAML → `DisplayName` для тех же длин меняется; тест с
> двумя версиями таблицы.

Реализация — трёхпортовая:

- `IBalanceConfig.get()` — снимок до reload-а (нужен для `before` в аудите).
- `IBalanceReloader.reload()` — собственно hot-reload (атомарный, в
  случае невалидного нового файла — старый снимок остаётся).
- `IAdminRepository.get_by_tg_id(...)` — RBAC.
- `IAuditLogger` + `IUnitOfWork` — атомарная запись в `audit_log`.

Сам `reload()` не транзакционен (это in-memory-операция); аудит-запись
пишется **после** успешного reload в отдельной короткой транзакции.
При неуспехе `reload()` мы аудит не пишем — состояние бота не
изменилось.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import IAdminRepository
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

    __slots__ = ("_admins", "_audit", "_balance", "_clock", "_reloader", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        balance: IBalanceConfig,
        reloader: IBalanceReloader,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._balance = balance
        self._reloader = reloader
        self._audit = audit
        self._clock = clock

    async def execute(self, *, actor_tg_id: int) -> ReloadBalanceResult:
        """Выполнить hot-reload `balance.yaml`.

        Шаги:

        1. Проверить, что `actor_tg_id` — активный админ с правом записи
           в баланс. Иначе — `AuthorizationError`.
        2. Зафиксировать `version_before` через read-порт.
        3. Вызвать `reloader.reload()`. При ошибке — пробрасываем
           `ConfigError` дальше; аудит не пишем (нет state change).
        4. Записать `BALANCE_RELOAD` в audit_log внутри короткой
           UoW-транзакции.
        """
        admin = await self._admins.get_by_tg_id(actor_tg_id)
        if admin is None or not admin.can_write_balance():
            raise AuthorizationError(
                requirement="admin_balance_write",
                detail=f"actor tg_id={actor_tg_id} cannot reload balance",
            )

        version_before = self._balance.get().version
        new_snapshot = self._reloader.reload()
        version_after = new_snapshot.version

        async with self._uow:
            now = self._clock.now()
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
