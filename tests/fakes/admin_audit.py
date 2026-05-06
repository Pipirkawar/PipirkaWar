"""Фейк `IAdminAuditLogger`. In-memory список записей для assert-ов в тестах."""

from __future__ import annotations

from pipirik_wars.domain.admin import AdminAuditEntry, IAdminAuditLogger


class FakeAdminAuditLogger(IAdminAuditLogger):
    """In-memory."""

    __slots__ = ("entries",)

    def __init__(self) -> None:
        self.entries: list[AdminAuditEntry] = []

    async def record(self, entry: AdminAuditEntry) -> None:
        self.entries.append(entry)
