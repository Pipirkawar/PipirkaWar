"""Фейк `IAdminAuditQuery`. In-memory `list_recent` для unit-тестов."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditRecord,
    IAdminAuditQuery,
)


@dataclass
class FakeAdminAuditQuery(IAdminAuditQuery):
    """In-memory `IAdminAuditQuery`.

    Тесты могут заполнять `records` напрямую (записи в любом порядке);
    `list_recent` сам сортирует по `(occurred_at DESC, id DESC)` и
    применяет фильтры.
    """

    records: list[AdminAuditRecord] = field(default_factory=list)

    async def list_recent(
        self,
        *,
        limit: int,
        target_admin_id: int | None = None,
        action: AdminAuditAction | None = None,
    ) -> Sequence[AdminAuditRecord]:
        rows = self.records
        if target_admin_id is not None:
            rows = [r for r in rows if r.actor_admin_id == target_admin_id]
        if action is not None:
            rows = [r for r in rows if r.action is action]
        rows = sorted(rows, key=lambda r: (r.occurred_at, r.id), reverse=True)
        return tuple(rows[:limit])
