"""Use-case `BootstrapSuperAdmin`.

Идея (ГДД §18.6.4):

1. На запуске бота мы хотим иметь хотя бы одного `super_admin`-а,
   иначе никто не сможет выдавать остальных админов.
2. Bootstrap **только один раз**: если в таблице `admins` есть хотя бы
   один активный аккаунт — env-переменная `BOOTSTRAP_ADMIN_IDS`
   игнорируется. Это защищает от случая «кто-то из злоумышленников
   получил доступ к env и пытается восстановить себе права после
   того, как реальный super_admin его исключил».
3. Все добавленные через bootstrap аккаунты пишутся в `audit_log`
   с reason="bootstrap" и `actor_id=NULL` (системное действие).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.admin import AdminRole, IAdminRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Что произошло при попытке bootstrap-а."""

    skipped_reason: str | None
    """Причина, по которой bootstrap не выполнялся, или `None`, если выполнялся."""

    granted_tg_ids: tuple[int, ...] = field(default=())
    """`tg_id`, которым выданы super_admin-права (только для свежевыданных)."""


class BootstrapSuperAdmin:
    """Use-case bootstrap-а первого `super_admin`-а."""

    __slots__ = ("_admins", "_audit", "_clock")

    def __init__(
        self,
        *,
        admins: IAdminRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._admins = admins
        self._audit = audit
        self._clock = clock

    async def execute(self, *, tg_ids: Iterable[int]) -> BootstrapResult:
        ids = tuple(dict.fromkeys(tg_ids))  # uniq, сохраняя порядок
        if not ids:
            return BootstrapResult(skipped_reason="no_ids_provided")

        existing_active = await self._admins.count_active()
        if existing_active > 0:
            return BootstrapResult(skipped_reason="admins_table_not_empty")

        granted: list[int] = []
        now = self._clock.now()
        for tg_id in ids:
            await self._admins.add(
                tg_id=tg_id,
                role=AdminRole.SUPER_ADMIN,
                created_by_admin_id=None,
                note="bootstrap",
            )
            await self._audit.record(
                _bootstrap_audit_entry(tg_id=tg_id, occurred_at=now),
            )
            granted.append(tg_id)

        return BootstrapResult(skipped_reason=None, granted_tg_ids=tuple(granted))


def _bootstrap_audit_entry(*, tg_id: int, occurred_at: datetime) -> AuditEntry:
    return AuditEntry(
        action=AuditAction.ADMIN_COMMAND,
        actor_id=None,
        target_kind="admin",
        target_id=str(tg_id),
        before=None,
        after={"role": AdminRole.SUPER_ADMIN.value, "is_active": True},
        reason="bootstrap super_admin from BOOTSTRAP_ADMIN_IDS",
        idempotency_key=None,
        occurred_at=occurred_at,
    )
