"""In-memory реализация `IBossFightRepository` / `IBossParticipantRepository`.

Зеркало `SqlAlchemyBossFightRepository` / `SqlAlchemyBossParticipantRepository`
(Спринт 3.3-B): partial unique-индекс «один саммонер на boss_fight» для
`is_summoner=True`, partial unique-индекс «один игрок-рейдер per boss_fight»,
serial id для `BossFight`, `IntegrityError` для дублей и несуществующих id
в `save()`.

`FakeBossFightRepository.get_active_for_player` имитирует JOIN с участниками
через явную ссылку `participants`. По умолчанию ссылка `None` — тогда метод
ищет только по роли «босс» (`boss_player_id`). При установленной ссылке
дополнительно учитывается роль «саммонер/рейдер» (через
`boss_participants.player_id`). Это даёт полное покрытие определения
«активный» из контракта.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossParticipant,
    IBossFightRepository,
    IBossParticipantRepository,
)
from pipirik_wars.shared.errors import IntegrityError

_ACTIVE_STATUSES = (BossFightStatus.LOBBY, BossFightStatus.IN_BATTLE)


@dataclass
class FakeBossParticipantRepository(IBossParticipantRepository):
    """In-memory реализация для тестов use-case-ов рейд-боссов."""

    rows: list[BossParticipant] = field(default_factory=list)

    async def add(self, participant: BossParticipant) -> BossParticipant:
        if any(
            existing.boss_fight_id == participant.boss_fight_id
            and existing.player_id == participant.player_id
            for existing in self.rows
        ):
            raise IntegrityError(
                f"player_id={participant.player_id} already participates "
                f"in boss_fight_id={participant.boss_fight_id}",
            )
        if participant.is_summoner and any(
            existing.boss_fight_id == participant.boss_fight_id and existing.is_summoner
            for existing in self.rows
        ):
            raise IntegrityError(
                f"boss_fight_id={participant.boss_fight_id} already has a summoner",
            )
        self.rows.append(participant)
        return participant

    async def list_by_boss_fight(
        self,
        *,
        boss_fight_id: int,
    ) -> tuple[BossParticipant, ...]:
        return tuple(
            sorted(
                (p for p in self.rows if p.boss_fight_id == boss_fight_id),
                key=lambda p: p.joined_at,
            )
        )

    async def get_by_boss_fight_and_player(
        self,
        *,
        boss_fight_id: int,
        player_id: int,
    ) -> BossParticipant | None:
        for p in self.rows:
            if p.boss_fight_id == boss_fight_id and p.player_id == player_id:
                return p
        return None

    async def remove(self, *, boss_fight_id: int, player_id: int) -> None:
        for i, p in enumerate(self.rows):
            if p.boss_fight_id == boss_fight_id and p.player_id == player_id:
                del self.rows[i]
                return


@dataclass
class FakeBossFightRepository(IBossFightRepository):
    """In-memory реализация для тестов use-case-ов рейд-боссов.

    `participants` — опциональная ссылка на репо рейдеров для имитации
    JOIN-а в `get_active_for_player`. Если `None`, то метод видит игрока
    только в роли «босс» (через `boss_player_id`).
    """

    rows: list[BossFight] = field(default_factory=list)
    participants: FakeBossParticipantRepository | None = None

    async def add(self, boss_fight: BossFight) -> BossFight:
        if boss_fight.id is not None:
            raise IntegrityError(
                f"BossFight with pre-set id={boss_fight.id} cannot be added; use save()",
            )
        new_id = (max((bf.id or 0 for bf in self.rows), default=0)) + 1
        saved = replace(boss_fight, id=new_id)
        self.rows.append(saved)
        return saved

    async def get_by_id(self, *, boss_fight_id: int) -> BossFight | None:
        for bf in self.rows:
            if bf.id == boss_fight_id:
                return bf
        return None

    async def get_active_for_player(self, *, player_id: int) -> BossFight | None:
        # Игрок может быть в активном рейде в одной из двух ролей:
        # 1) босс — через `boss_fights.boss_player_id`;
        # 2) саммонер/рейдер — через `boss_participants.player_id`.
        active = [bf for bf in self.rows if bf.status in _ACTIVE_STATUSES]
        # Сортируем по `started_at` DESC — берём самый свежий.
        active.sort(key=lambda bf: bf.started_at, reverse=True)
        raider_fight_ids: set[int] = set()
        if self.participants is not None:
            raider_fight_ids = {
                p.boss_fight_id for p in self.participants.rows if p.player_id == player_id
            }
        for bf in active:
            if bf.boss_player_id == player_id:
                return bf
            if bf.id is not None and bf.id in raider_fight_ids:
                return bf
        return None

    async def get_last_global_started_at(self) -> datetime | None:
        last: datetime | None = None
        for bf in self.rows:
            if last is None or bf.started_at > last:
                last = bf.started_at
        return last

    async def save(self, boss_fight: BossFight) -> BossFight:
        if boss_fight.id is None:
            raise IntegrityError("BossFight.save requires id; use add() for new boss fights")
        for i, existing in enumerate(self.rows):
            if existing.id == boss_fight.id:
                self.rows[i] = boss_fight
                return boss_fight
        raise IntegrityError(f"BossFight id={boss_fight.id} does not exist")
