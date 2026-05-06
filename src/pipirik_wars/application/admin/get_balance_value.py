"""Use-case `GetBalanceValue` (Спринт 2.5-C.3, ГДД §18.6.4).

`/balance_get <key>` — read-only чтение балансового ключа. **Без TOTP**
(read-side не разрушительный). Логируется `ADMIN_BALANCE_GET` (как и
`ADMIN_PLAYER_LOOKUP` — нужен super-admin-у в `/audit <admin>` для
понимания, кто пробивал балансовые константы).

Алгоритм:

1. Авторизация: актор активный админ.
2. Выгружаем актуальный `BalanceConfig` через `IBalanceConfig.get()`.
3. Резолвим dotted-path через `lookup_path(...)`.
4. Audit `ADMIN_BALANCE_GET` (внутри UoW).
5. Возвращаем `(key, raw_value, version_at_read)`.

Ошибки:

- `BalanceKeyError(reason="empty"|"not_found"|"index_invalid")` — handler
  переводит в `admin-balance-get-key-not-found`.
- `AuthorizationError` — стандартный.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipirik_wars.application.admin._balance_path import lookup_path
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminRepository,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class GetBalanceValueInput:
    actor_tg_id: int
    key: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class GetBalanceValueOutput:
    key: str
    raw_value: Any
    balance_version: int


class GetBalanceValue:
    """Use-case чтения балансового ключа (read-only, audit включён)."""

    __slots__ = ("_admins", "_audit", "_balance", "_clock", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        balance: IBalanceConfig,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: GetBalanceValueInput) -> GetBalanceValueOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        snapshot = self._balance.get()
        # Поднимем `BalanceKeyError` ДО открытия UoW — у нас нет транзакционных
        # изменений, и нам не нужно платить за no-op-транзакцию.
        raw_value = lookup_path(snapshot, inp.key)

        now = self._clock.now()
        async with self._uow:
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_BALANCE_GET,
                    target_kind="balance_key",
                    target_id=inp.key,
                    before=None,
                    after=None,
                    reason=f"balance_get:{inp.key}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return GetBalanceValueOutput(
            key=inp.key,
            raw_value=raw_value,
            balance_version=snapshot.version,
        )


__all__ = ["GetBalanceValue", "GetBalanceValueInput", "GetBalanceValueOutput"]
