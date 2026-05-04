"""In-memory реализация репозиториев клана и членств.

Соответствует поведению SQLAlchemy-реализации:
- `IClanRepository.add(...)` бросает `ClanAlreadyRegisteredError` при
  дубле `chat_id`;
- `IClanMembershipRepository.add(...)` бросает
  `ClanMembershipExistsError` при дубле `(clan_id, player_id)`;
- `remove(...)` идемпотентен.

В дополнение fake-репозиторий членств моделирует БД-инвариант
`UNIQUE(player_id)` (один игрок = один клан): если игрок уже состоит
в **другом** клане, `add(...)` тоже бросает `ClanMembershipExistsError`
(это критично для unit-теста JoinClan-а, проверяющего ГДД §4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from pipirik_wars.domain.clan import (
    Clan,
    ClanAlreadyRegisteredError,
    ClanMember,
    ClanMembershipExistsError,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeClanRepository(IClanRepository):
    rows: list[Clan] = field(default_factory=list)

    async def get_by_chat_id(self, chat_id: int) -> Clan | None:
        for c in self.rows:
            if c.chat_id == chat_id:
                return c
        return None

    async def get_by_id(self, clan_id: int) -> Clan | None:
        for c in self.rows:
            if c.id == clan_id:
                return c
        return None

    async def add(self, clan: Clan) -> Clan:
        if clan.id is not None:
            raise IntegrityError(f"Clan with pre-set id={clan.id} cannot be added; use save()")
        if any(existing.chat_id == clan.chat_id for existing in self.rows):
            raise ClanAlreadyRegisteredError(chat_id=clan.chat_id)
        new_id = (max((c.id or 0 for c in self.rows), default=0)) + 1
        saved = replace(clan, id=new_id)
        self.rows.append(saved)
        return saved

    async def save(self, clan: Clan) -> Clan:
        if clan.id is None:
            raise IntegrityError("Clan without id cannot be saved; use add() for new clans")
        for i, existing in enumerate(self.rows):
            if existing.id == clan.id:
                self.rows[i] = clan
                return clan
        raise IntegrityError(f"Clan id={clan.id} does not exist")


@dataclass
class FakeClanMembershipRepository(IClanMembershipRepository):
    rows: list[ClanMember] = field(default_factory=list)

    async def get_by_player(self, player_id: int) -> ClanMember | None:
        for m in self.rows:
            if m.player_id == player_id:
                return m
        return None

    async def list_by_clan(self, clan_id: int) -> Sequence[ClanMember]:
        return tuple(m for m in self.rows if m.clan_id == clan_id)

    async def add(self, member: ClanMember) -> ClanMember:
        # Сначала — UNIQUE(player_id): один игрок — один клан (ГДД §4).
        if any(m.player_id == member.player_id for m in self.rows):
            raise ClanMembershipExistsError(
                clan_id=member.clan_id,
                player_id=member.player_id,
            )
        # На всякий случай — точный дубль `(clan_id, player_id)`
        # (теоретически уже отловлено выше).
        if any(m.clan_id == member.clan_id and m.player_id == member.player_id for m in self.rows):
            raise ClanMembershipExistsError(
                clan_id=member.clan_id,
                player_id=member.player_id,
            )
        self.rows.append(member)
        return member

    async def remove(self, *, clan_id: int, player_id: int) -> bool:
        for i, m in enumerate(self.rows):
            if m.clan_id == clan_id and m.player_id == player_id:
                del self.rows[i]
                return True
        return False
