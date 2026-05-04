"""In-memory `ISignupQueueRepository` для unit-тестов."""

from __future__ import annotations

from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
    SignupQueueEntry,
)


class FakeSignupQueueRepository(ISignupQueueRepository):
    """FIFO в `list[SignupQueueEntry]` с автонумерацией `id`."""

    __slots__ = ("_next_id", "_rows")

    def __init__(self) -> None:
        self._rows: list[SignupQueueEntry] = []
        self._next_id = 1

    @property
    def rows(self) -> tuple[SignupQueueEntry, ...]:
        return tuple(self._rows)

    async def enqueue(self, *, entry: SignupQueueEntry) -> SignupQueueEntry:
        if any(row.tg_id == entry.tg_id for row in self._rows):
            raise AlreadyQueuedError(tg_id=entry.tg_id)
        new_entry = SignupQueueEntry(
            id=self._next_id,
            tg_id=entry.tg_id,
            username=entry.username,
            locale=entry.locale,
            position=len(self._rows) + 1,
            enqueued_at=entry.enqueued_at,
        )
        self._rows.append(new_entry)
        self._next_id += 1
        return new_entry

    async def get_by_tg_id(self, tg_id: int) -> SignupQueueEntry | None:
        for index, row in enumerate(self._rows):
            if row.tg_id == tg_id:
                return SignupQueueEntry(
                    id=row.id,
                    tg_id=row.tg_id,
                    username=row.username,
                    locale=row.locale,
                    position=index + 1,
                    enqueued_at=row.enqueued_at,
                )
        return None

    async def size(self) -> int:
        return len(self._rows)

    async def pop_front(self, *, limit: int) -> list[SignupQueueEntry]:
        if limit <= 0:
            return []
        head = self._rows[:limit]
        self._rows = self._rows[limit:]
        return [
            SignupQueueEntry(
                id=row.id,
                tg_id=row.tg_id,
                username=row.username,
                locale=row.locale,
                position=index + 1,
                enqueued_at=row.enqueued_at,
            )
            for index, row in enumerate(head)
        ]
