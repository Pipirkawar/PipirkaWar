"""In-memory реализация `IGlobalLobbyRepository` (Спринт 2.1.F).

Имитирует ключевое поведение `SqlAlchemyGlobalLobbyRepository`:

- `enqueue(duel_id=…, enqueued_at=…)` — идемпотентно: повторная попытка
  поставить уже стоящую дуэль возвращает `False` и НЕ обновляет
  `enqueued_at` (FIFO-инвариант — первоначальный момент сохраняется).
- `pop_oldest()` — извлекает запись с минимальным `enqueued_at`
  (FIFO) и атомарно удаляет её.
- `remove(duel_id=…)` — идемпотентно (no-op, если записи нет);
  `True` если что-то реально удалили.
- `is_in_lobby(duel_id=…)` — read-only проверка наличия.

Не моделирует «откат» при rollback (для этого есть `FakeUnitOfWork`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository, LobbyEntry


@dataclass
class FakeGlobalLobbyRepository(IGlobalLobbyRepository):
    """In-memory реализация для тестов use-case-ов глобального лобби PvP."""

    rows: list[LobbyEntry] = field(default_factory=list)

    async def enqueue(self, *, duel_id: int, enqueued_at: datetime) -> bool:
        for existing in self.rows:
            if existing.duel_id == duel_id:
                return False
        self.rows.append(LobbyEntry(duel_id=duel_id, enqueued_at=enqueued_at))
        return True

    async def pop_oldest(self) -> LobbyEntry | None:
        if not self.rows:
            return None
        oldest_idx = min(range(len(self.rows)), key=lambda i: self.rows[i].enqueued_at)
        return self.rows.pop(oldest_idx)

    async def remove(self, *, duel_id: int) -> bool:
        for i, existing in enumerate(self.rows):
            if existing.duel_id == duel_id:
                self.rows.pop(i)
                return True
        return False

    async def is_in_lobby(self, *, duel_id: int) -> bool:
        return any(r.duel_id == duel_id for r in self.rows)
