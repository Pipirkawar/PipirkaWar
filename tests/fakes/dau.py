"""In-memory тест-fake-и для DAU-портов."""

from __future__ import annotations

from pipirik_wars.domain.dau import IDauCounter, IDauLimit


class FakeDauCounter(IDauCounter):
    """Простейший счётчик активных без сброса по дате (для unit-тестов)."""

    def __init__(self, *, initial: int = 0) -> None:
        self._actives: set[int] = set()
        self._initial = initial

    async def record_active(self, *, tg_user_id: int) -> None:
        self._actives.add(tg_user_id)

    async def current(self) -> int:
        return self._initial + len(self._actives)

    def force_set(self, *, value: int) -> None:
        """Test-helper: явно подменить значение `current()` (без `record_active`)."""
        self._initial = value
        self._actives.clear()


class FakeDauLimit(IDauLimit):
    """In-memory `MAX_DAU` без `asyncio.Lock` — для unit-тестов."""

    def __init__(self, *, initial: int = 200) -> None:
        if initial < 1:
            msg = f"initial must be >= 1, got {initial}"
            raise ValueError(msg)
        self._max_dau = initial

    async def get(self) -> int:
        return self._max_dau

    async def set(self, *, max_dau: int) -> int:
        if max_dau < 1:
            msg = f"max_dau must be >= 1, got {max_dau}"
            raise ValueError(msg)
        previous = self._max_dau
        self._max_dau = max_dau
        return previous
