"""In-memory реализация `IMassDuelRepository` для unit-тестов use-case-ов
массового PvP (Спринт 2.2.D / 2.2.E).

Имитирует ключевое поведение `SqlAlchemyMassDuelRepository`:

- `add(duel)` без `id` присваивает следующий serial и возвращает копию
  с `id`; попытка добавить с уже выставленным `id` → `IntegrityError`;
- `get_by_id` возвращает агрегат по `id`, либо `None`;
- `save(duel)` обновляет запись по `id`; отсутствующий id или
  несуществующая запись → `IntegrityError`. Дополнительно проверяет
  frozen-roster-инвариант (`clan{1,2}_member_ids` нельзя менять
  между `add(...)` и `save(...)`).

Не моделирует «откат» при rollback (для этого есть `FakeUnitOfWork`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pipirik_wars.domain.pvp.mass_duel import MassDuel
from pipirik_wars.domain.pvp.repositories import IMassDuelRepository
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeMassDuelRepository(IMassDuelRepository):
    """In-memory реализация для тестов use-case-ов массового PvP."""

    rows: list[MassDuel] = field(default_factory=list)

    async def add(self, duel: MassDuel) -> MassDuel:
        if duel.id is not None:
            raise IntegrityError(
                f"MassDuel with pre-set id={duel.id} cannot be added; use save()",
            )
        new_id = (max((d.id or 0 for d in self.rows), default=0)) + 1
        saved = replace(duel, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, duel_id: int) -> MassDuel | None:
        for d in self.rows:
            if d.id == duel_id:
                return d
        return None

    async def find_most_recent_for_clan(self, *, clan_id: int) -> MassDuel | None:
        candidates = [d for d in self.rows if clan_id in (d.clan1_id, d.clan2_id)]
        if not candidates:
            return None
        candidates.sort(
            key=lambda d: (d.created_at, d.id or 0),
            reverse=True,
        )
        return candidates[0]

    async def save(self, duel: MassDuel) -> MassDuel:
        if duel.id is None:
            raise IntegrityError(
                "MassDuel.save requires id; use add() for new mass-duels",
            )
        for i, existing in enumerate(self.rows):
            if existing.id == duel.id:
                if (
                    existing.clan1_member_ids != duel.clan1_member_ids
                    or existing.clan2_member_ids != duel.clan2_member_ids
                ):
                    raise IntegrityError(
                        f"MassDuel id={duel.id} roster mismatch:"
                        " cannot change participants between add() and save()",
                    )
                self.rows[i] = duel
                return duel
        raise IntegrityError(f"MassDuel id={duel.id} does not exist")
