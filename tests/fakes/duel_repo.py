"""In-memory реализация `IDuelRepository` для unit-тестов use-case-ов PvP.

Имитирует ключевое поведение `SqlAlchemyDuelRepository`:

- `add(duel)` без `id` присваивает следующий serial и возвращает копию
  с `id`; попытка добавить с уже выставленным `id` → `IntegrityError`;
- `get_by_id` возвращает агрегат по `id` (со всеми completed-раундами
  и `pending_round`), либо `None`;
- `save(duel)` обновляет запись по `id`; отсутствующий id или
  несуществующая запись → `IntegrityError`.

Не моделирует «откат» при rollback (для этого есть `FakeUnitOfWork`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pipirik_wars.domain.pvp.duel import Duel
from pipirik_wars.domain.pvp.repositories import IDuelRepository
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeDuelRepository(IDuelRepository):
    """In-memory реализация для тестов use-case-ов PvP."""

    rows: list[Duel] = field(default_factory=list)

    async def add(self, duel: Duel) -> Duel:
        if duel.id is not None:
            raise IntegrityError(
                f"Duel with pre-set id={duel.id} cannot be added; use save()",
            )
        new_id = (max((d.id or 0 for d in self.rows), default=0)) + 1
        saved = replace(duel, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, duel_id: int) -> Duel | None:
        for d in self.rows:
            if d.id == duel_id:
                return d
        return None

    async def save(self, duel: Duel) -> Duel:
        if duel.id is None:
            raise IntegrityError("Duel.save requires id; use add() for new duels")
        for i, existing in enumerate(self.rows):
            if existing.id == duel.id:
                self.rows[i] = duel
                return duel
        raise IntegrityError(f"Duel id={duel.id} does not exist")
