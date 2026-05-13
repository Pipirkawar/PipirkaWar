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
    ClanStatus,
    ClanTopEntry,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import Player, PlayerStatus
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeClanRepository(IClanRepository):
    rows: list[Clan] = field(default_factory=list)
    # Доп. источник для агрегации `list_top_by_total_length`. Заполняется
    # тестом через `seed_player`/`seed_membership`. Реальный SQL-репо
    # делает SQL-агрегацию по таблицам `players` × `clan_members`.
    members: list[ClanMember] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)

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

    async def list_top_by_total_length(self, *, limit: int) -> Sequence[ClanTopEntry]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        # Агрегация: для каждого ACTIVE-клана считаем сумму длин и
        # количество ACTIVE-участников. Кланы с 0 ACTIVE-участников
        # исключаются (см. контракт `IClanRepository.list_top_by_total_length`).
        active_clans = [c for c in self.rows if c.status is ClanStatus.ACTIVE and c.id is not None]
        active_player_ids = {
            p.id for p in self.players if p.id is not None and p.status is PlayerStatus.ACTIVE
        }
        player_length: dict[int, int] = {
            p.id: p.length.cm
            for p in self.players
            if p.id is not None and p.status is PlayerStatus.ACTIVE
        }
        entries: list[ClanTopEntry] = []
        for clan in active_clans:
            assert clan.id is not None
            members = [
                m for m in self.members if m.clan_id == clan.id and m.player_id in active_player_ids
            ]
            if not members:
                continue
            total = sum(player_length.get(m.player_id, 0) for m in members)
            entries.append(
                ClanTopEntry(
                    clan_id=clan.id,
                    clan_title=clan.title,
                    total_length_cm=total,
                    member_count=len(members),
                ),
            )
        entries.sort(key=lambda e: (-e.total_length_cm, e.clan_id))
        return tuple(entries[:limit])

    async def list_active(self) -> Sequence[Clan]:
        active = [c for c in self.rows if c.status is ClanStatus.ACTIVE]
        active.sort(key=lambda c: c.id or 0)
        return tuple(active)

    async def list_all(
        self,
        *,
        status_filter: ClanStatus | None = None,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Clan]:
        filtered = self.rows
        if status_filter is not None:
            filtered = [c for c in filtered if c.status is status_filter]
        filtered.sort(key=lambda c: c.id or 0)
        return tuple(filtered[offset : offset + limit])

    async def count_all(self, *, status_filter: ClanStatus | None = None) -> int:
        if status_filter is None:
            return len(self.rows)
        return sum(1 for c in self.rows if c.status is status_filter)

    async def count_active_for_player(
        self,
        *,
        player_id: int,
        min_tribe_size: int,
    ) -> int:
        # Бонус-за-племена (ГДД §11.1, Спринт 3.6-A): количество активных
        # кланов, где состоит `player_id` и общее число `clan_members`
        # >= `min_tribe_size`. Frozen-кланы исключены.
        if min_tribe_size < 1:
            raise ValueError(f"min_tribe_size must be >= 1, got {min_tribe_size}")
        active_clans_by_id = {
            c.id: c for c in self.rows if c.status is ClanStatus.ACTIVE and c.id is not None
        }
        # Собираем размер каждого активного клана и проверяем членство игрока.
        clan_to_size: dict[int, int] = {}
        clan_to_has_player: dict[int, bool] = {}
        for m in self.members:
            if m.clan_id not in active_clans_by_id:
                continue
            clan_to_size[m.clan_id] = clan_to_size.get(m.clan_id, 0) + 1
            if m.player_id == player_id:
                clan_to_has_player[m.clan_id] = True
        return sum(
            1
            for clan_id, size in clan_to_size.items()
            if size >= min_tribe_size and clan_to_has_player.get(clan_id, False)
        )


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
