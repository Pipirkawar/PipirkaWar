"""In-memory реализация `ICaravanRepository` / `ICaravanParticipantRepository`.

Зеркало `SqlAlchemyCaravanRepository` / `SqlAlchemyCaravanParticipantRepository`
(Спринт 3.2-B): partial unique-индекс «один активный караван на
sender_clan_id» для активных статусов (`LOBBY`/`IN_BATTLE`),
serial id для каравана, `IntegrityError` для дублей и несуществующих id
в `save()`. У участников — `UNIQUE (caravan_id, player_id)` через
проверку при `add()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanParticipant,
    CaravanRole,
    CaravanStatus,
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.shared.errors import IntegrityError

_ACTIVE_STATUSES = (CaravanStatus.LOBBY, CaravanStatus.IN_BATTLE)


@dataclass
class FakeCaravanRepository(ICaravanRepository):
    """In-memory реализация для тестов use-case-ов каравана."""

    rows: list[Caravan] = field(default_factory=list)

    async def add(self, caravan: Caravan) -> Caravan:
        if caravan.id is not None:
            raise IntegrityError(
                f"Caravan with pre-set id={caravan.id} cannot be added; use save()",
            )
        if caravan.status in _ACTIVE_STATUSES and any(
            existing.sender_clan_id == caravan.sender_clan_id
            and existing.status in _ACTIVE_STATUSES
            for existing in self.rows
        ):
            raise IntegrityError(
                f"sender_clan_id={caravan.sender_clan_id} already has an active caravan",
            )
        new_id = (max((c.id or 0 for c in self.rows), default=0)) + 1
        saved = replace(caravan, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, caravan_id: int) -> Caravan | None:
        for c in self.rows:
            if c.id == caravan_id:
                return c
        return None

    async def get_active_by_clan(self, *, clan_id: int) -> Caravan | None:
        for c in self.rows:
            if c.sender_clan_id == clan_id and c.status in _ACTIVE_STATUSES:
                return c
        return None

    async def get_last_finished_at_for_clan(self, *, clan_id: int) -> datetime | None:
        last: datetime | None = None
        for c in self.rows:
            if c.sender_clan_id != clan_id:
                continue
            if last is None or c.started_at > last:
                last = c.started_at
        return last

    async def save(self, caravan: Caravan) -> Caravan:
        if caravan.id is None:
            raise IntegrityError("Caravan.save requires id; use add() for new caravans")
        for i, existing in enumerate(self.rows):
            if existing.id == caravan.id:
                self.rows[i] = caravan
                return caravan
        raise IntegrityError(f"Caravan id={caravan.id} does not exist")


@dataclass
class FakeCaravanParticipantRepository(ICaravanParticipantRepository):
    """In-memory реализация для тестов use-case-ов каравана."""

    rows: list[CaravanParticipant] = field(default_factory=list)

    async def add(self, participant: CaravanParticipant) -> CaravanParticipant:
        if any(
            existing.caravan_id == participant.caravan_id
            and existing.player_id == participant.player_id
            for existing in self.rows
        ):
            raise IntegrityError(
                f"player_id={participant.player_id} already participates "
                f"in caravan_id={participant.caravan_id}",
            )
        self.rows.append(participant)
        return participant

    async def list_by_caravan(
        self,
        *,
        caravan_id: int,
    ) -> tuple[CaravanParticipant, ...]:
        return tuple(
            sorted(
                (p for p in self.rows if p.caravan_id == caravan_id),
                key=lambda p: p.joined_at,
            )
        )

    async def list_by_caravan_and_role(
        self,
        *,
        caravan_id: int,
        role: CaravanRole,
    ) -> tuple[CaravanParticipant, ...]:
        return tuple(
            sorted(
                (p for p in self.rows if p.caravan_id == caravan_id and p.role is role),
                key=lambda p: p.joined_at,
            )
        )

    async def remove(self, *, caravan_id: int, player_id: int) -> None:
        for i, p in enumerate(self.rows):
            if p.caravan_id == caravan_id and p.player_id == player_id:
                del self.rows[i]
                return
