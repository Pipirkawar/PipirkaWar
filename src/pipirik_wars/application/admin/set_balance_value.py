"""Use-case `SetBalanceValue` (Спринт 2.5-C.4, ГДД §16 / §18.6.4).

`/balance_set <key> <raw_value>` — правка балансового ключа в YAML
с TOTP-подтверждением. Запись идёт через `IBalanceWriter`
(atomic-write + auto-reload). Audit `ADMIN_BALANCE_SET` пишется
**до** записи, чтобы при сбое writer-а у нас в логах остался след
о попытке.

Алгоритм:

1. Авторизация: актор активный админ.
2. Open UoW.
3. Idempotency check: если ключ уже виден → вернуть текущее значение
   как replay (`was_idempotent_replay=True`, audit не пишется).
4. Прочитать текущее значение через `lookup_path` (для `before`).
5. Если новое == старое → no-op (`was_already_at_value=True`,
   audit не пишется, idempotency.mark всё равно ставим).
6. Записать audit `ADMIN_BALANCE_SET` (commit транзакции по выходу
   из `async with`).
7. Записать в YAML через `IBalanceWriter.write_value(...)` (вне
   UoW — IO-операция, не должна откатываться при сбое транзакции).
8. Mark idempotency.

Ошибки:

- `BalanceKeyError` (из `IBalanceWriter` или нашего `lookup_path`)
- `ConfigError` (если новое значение нарушает pydantic-инвариант)
- `AuthorizationError`
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.admin._balance_path import lookup_path
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.balance.errors import BalanceKeyError
from pipirik_wars.domain.balance.ports import IBalanceConfig, IBalanceWriter
from pipirik_wars.domain.shared.ports import IClock, IIdempotencyKey, IUnitOfWork

_IDEMPOTENCY_NAMESPACE = "admin_balance_set"


@dataclass(frozen=True, slots=True)
class SetBalanceValueInput:
    actor_tg_id: int
    key: str
    raw_value: Any
    reason: str
    idempotency_key: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class SetBalanceValueOutput:
    key: str
    previous_raw_value: Any
    new_raw_value: Any
    new_balance_version: int
    was_already_at_value: bool
    was_idempotent_replay: bool


class SetBalanceValue:
    """Use-case записи балансового ключа (после TOTP-подтверждения)."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_balance",
        "_clock",
        "_idempotency",
        "_uow",
        "_writer",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        balance: IBalanceConfig,
        writer: IBalanceWriter,
        idempotency: IIdempotencyKey,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._balance = balance
        self._writer = writer
        self._idempotency = idempotency
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: SetBalanceValueInput) -> SetBalanceValueOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        if not inp.reason or not inp.reason.strip():
            raise ValueError("SetBalanceValue.reason must be a non-empty string")
        reason = inp.reason.strip()

        # Snapshot до открытия UoW — нужен и для replay-ветки, и для before/after.
        snapshot_before = self._balance.get()
        # Поднимет BalanceKeyError если ключ невалиден — раньше, чем UoW.
        previous_raw = lookup_path(snapshot_before, inp.key)

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.SET_BALANCE_VALUE,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="balance_key",
            target_id=inp.key,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )
        async with self._uow:
            if await self._idempotency.is_seen(inp.idempotency_key):
                return SetBalanceValueOutput(
                    key=inp.key,
                    previous_raw_value=previous_raw,
                    new_raw_value=previous_raw,
                    new_balance_version=snapshot_before.version,
                    was_already_at_value=False,
                    was_idempotent_replay=True,
                )

            if previous_raw == inp.raw_value:
                # Domain-уровневая идемпотентность: значение уже такое.
                # Помечаем ключ, чтобы повтор пошёл по replay-ветке.
                await self._idempotency.mark(
                    inp.idempotency_key,
                    namespace=_IDEMPOTENCY_NAMESPACE,
                )
                return SetBalanceValueOutput(
                    key=inp.key,
                    previous_raw_value=previous_raw,
                    new_raw_value=previous_raw,
                    new_balance_version=snapshot_before.version,
                    was_already_at_value=True,
                    was_idempotent_replay=False,
                )

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_BALANCE_SET,
                    target_kind="balance_key",
                    target_id=inp.key,
                    before={"value": previous_raw},
                    after={"value": inp.raw_value},
                    reason=reason,
                    idempotency_key=inp.idempotency_key,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )
            await self._idempotency.mark(
                inp.idempotency_key,
                namespace=_IDEMPOTENCY_NAMESPACE,
            )

        # Запись на диск — ВНЕ UoW. Если БД-транзакция откатилась бы,
        # мы бы не хотели писать в файл. Если файл-write упадёт — у нас
        # уже есть audit-запись «попытка», что соответствует spec-у.
        new_snapshot = self._writer.write_value(key=inp.key, raw_value=inp.raw_value)

        return SetBalanceValueOutput(
            key=inp.key,
            previous_raw_value=previous_raw,
            new_raw_value=inp.raw_value,
            new_balance_version=new_snapshot.version,
            was_already_at_value=False,
            was_idempotent_replay=False,
        )


__all__ = [
    "BalanceKeyError",
    "SetBalanceValue",
    "SetBalanceValueInput",
    "SetBalanceValueOutput",
]
