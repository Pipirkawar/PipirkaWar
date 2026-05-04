"""Фейк audit-логгера. In-memory список записей для assert-ов в тестах."""

from __future__ import annotations

from pipirik_wars.domain.shared.ports import AuditEntry, IAuditLogger


class FakeAuditLogger(IAuditLogger):
    """In-memory."""

    __slots__ = ("entries",)

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)
