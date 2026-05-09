"""In-memory реализация `IRouletteSpinRepository` для unit-тестов use-case-ов.

Имитирует `SqlAlchemyRouletteSpinRepository` (Спринт 3.5-B):

* `record(spin)` — append-only вставка в `rows`. Идемпотентность по
  `idempotency_key`: повторный `record(...)` с тем же ключом — no-op
  (как `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` в проде).
* `last_free_spin_at(player_id)` — `MAX(occurred_at)` среди записей
  игрока; `None`, если игрок никогда не прокручивал.

Использование:

    repo = FakeRouletteSpinRepository()
    await repo.record(spin=RouletteSpin(...))
    last = await repo.last_free_spin_at(player_id=42)

Тесты use-case-а `SpinFreeRoulette` (Спринт 3.5-C) могут читать
`repo.rows` напрямую для проверки append-only-семантики и порядка.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.roulette import IRouletteSpinRepository, RouletteSpin


@dataclass
class FakeRouletteSpinRepository(IRouletteSpinRepository):
    """In-memory реализация для тестов use-case-а рулетки."""

    rows: list[RouletteSpin] = field(default_factory=list)

    async def record(self, *, spin: RouletteSpin) -> None:
        """Append-only вставка с идемпотентностью по `idempotency_key`."""
        for existing in self.rows:
            if existing.idempotency_key == spin.idempotency_key:
                # Дубликат ключа — тихий no-op, как в SqlAlchemy-impl.
                return
        self.rows.append(spin)

    async def last_free_spin_at(self, *, player_id: int) -> datetime | None:
        """`MAX(occurred_at)` среди записей игрока или `None`."""
        moments = [r.occurred_at for r in self.rows if r.player_id == player_id]
        if not moments:
            return None
        return max(moments)
