"""In-memory реализация `IPlayerRepository` для unit-тестов use-case-ов.

Старается воспроизводить поведение SQLAlchemy-репозитория настолько,
насколько это релевантно бизнес-логике: UNIQUE по `tg_id` бросает
`PlayerAlreadyRegisteredError`; `add()` без `id` — выдаёт следующий
по порядку serial; `save()` без существующего `id` — `IntegrityError`.

Не реализуем «откат» данных при rollback — использующие тесты сами
должны это учитывать (см. `FakeUnitOfWork`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
    PlayerAlreadyRegisteredError,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakePlayerRepository(IPlayerRepository):
    rows: list[Player] = field(default_factory=list)

    async def get_by_tg_id(self, tg_id: int) -> Player | None:
        for p in self.rows:
            if p.tg_id == tg_id:
                return p
        return None

    async def add(self, player: Player) -> Player:
        if player.id is not None:
            raise IntegrityError(f"Player with pre-set id={player.id} cannot be added; use save()")
        if any(existing.tg_id == player.tg_id for existing in self.rows):
            raise PlayerAlreadyRegisteredError(tg_id=player.tg_id)
        new_id = (max((p.id or 0 for p in self.rows), default=0)) + 1
        saved = replace(player, id=new_id)
        self.rows.append(saved)
        return saved

    async def save(self, player: Player) -> Player:
        if player.id is None:
            raise IntegrityError("Player without id cannot be saved; use add() for new players")
        for i, existing in enumerate(self.rows):
            if existing.id == player.id:
                self.rows[i] = player
                return player
        raise IntegrityError(f"Player id={player.id} does not exist")
