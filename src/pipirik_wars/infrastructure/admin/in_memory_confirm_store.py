"""In-memory реализация `IAdminConfirmStore` (Спринт 2.5-A.3).

Хранит ожидающие подтверждения в `dict[str, AdminConfirmEntry]` —
живёт ровно один процесс бота. Это намеренно: TTL у токена — 60
секунд, в случае рестарта токены всё равно теряют смысл.

`pop` — атомарный, чтобы исключить race на одновременном повторном
коде. `cleanup_expired` — фоновая очистка просроченных, чтобы dict
не рос бесконечно (вызывается из use-case-а или scheduled-task).
"""

from __future__ import annotations

from datetime import datetime

from pipirik_wars.domain.admin import AdminConfirmEntry, IAdminConfirmStore


class InMemoryAdminConfirmStore(IAdminConfirmStore):
    """Process-local store TOTP-подтверждений."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, AdminConfirmEntry] = {}

    async def save(self, *, token: str, entry: AdminConfirmEntry) -> None:
        self._entries[token] = entry

    async def pop(self, *, token: str) -> AdminConfirmEntry | None:
        return self._entries.pop(token, None)

    async def cleanup_expired(self, *, now: datetime) -> int:
        """Удалить все просроченные записи, вернуть, сколько удалено.

        Не часть `IAdminConfirmStore` — служебный метод фонового
        scheduled-job-а / тестов.
        """
        expired = [token for token, entry in self._entries.items() if entry.expires_at < now]
        for token in expired:
            del self._entries[token]
        return len(expired)


__all__ = ["InMemoryAdminConfirmStore"]
