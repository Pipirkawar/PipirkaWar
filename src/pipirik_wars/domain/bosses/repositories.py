"""Порты репозиториев домена «Рейд-боссы» (Спринт 3.3-A, ГДД §10).

Два порта:

- `IBossFightRepository` — CRUD для агрегата `BossFight`.
- `IBossParticipantRepository` — CRUD + listing для `BossParticipant`
  (ассоциативная таблица «рейдер ↔ рейд-бой»).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозитории не делают (правило Спринта 0.2).

Реализации — Спринт 3.3-B (SQLAlchemy + миграция `0020_boss_fights`).
"""

from __future__ import annotations

import abc
from datetime import datetime

from pipirik_wars.domain.bosses.entities import BossFight, BossParticipant


class IBossFightRepository(abc.ABC):
    """Доступ к таблице `boss_fights` (агрегат `BossFight`)."""

    @abc.abstractmethod
    async def add(self, boss_fight: BossFight) -> BossFight:
        """Добавить новый рейд-бой (`status=LOBBY`).

        На вход — `boss_fight.id is None`. Возвращает копию с
        проставленным `id`.
        """

    @abc.abstractmethod
    async def get_by_id(self, *, boss_fight_id: int) -> BossFight | None:
        """Найти рейд-бой по `id`, либо `None`."""

    @abc.abstractmethod
    async def get_active_for_player(self, *, player_id: int) -> BossFight | None:
        """Найти активный рейд-бой, в котором участвует `player_id`,
        либо `None`.

        Активный = `status in (LOBBY, IN_BATTLE)`. Учитываются обе
        роли — и саммонер/рейдер (через `boss_participants` JOIN),
        и босс (через `boss_player_id` напрямую). Гарантия: одновременно
        у одного игрока может быть **не более одного** активного
        рейд-боя (БД-инвариант через `activity_lock` и UNIQUE-индексы;
        миграция 3.3-B).
        """

    @abc.abstractmethod
    async def get_last_global_started_at(self) -> datetime | None:
        """Время последнего успешного `SummonBoss`-а на проекте.

        Используется `SummonBoss` (3.3-B) для проверки **глобального**
        4-часового кулдауна (ГДД §10.1: «1 раз в 4 часа (глобальный)»).
        Возвращает `None`, если ни одного рейд-боя ещё не было.

        Концептуально — `MAX(started_at) FROM boss_fights`. На уровне
        реализации это распределённый lock через UNIQUE-индекс на
        `boss_fights.started_at` с гранулярностью округления (детали —
        Спринт 3.3-B). Кулдаун стартует с `started_at`, не с
        `finished_at` — это значит, что отменённый бой тоже «съедает»
        кулдаун (по решению cyan91 на старте 3.3-A: «1 призыв в 4 часа
        на сервер, без re-roll-а на CANCELLED»).
        """

    @abc.abstractmethod
    async def save(self, boss_fight: BossFight) -> BossFight:
        """Обновить запись рейд-боя по `id`.

        Используется в 3.3-B/C для переходов:
        `LOBBY → IN_BATTLE`, `IN_BATTLE → FINISHED`,
        `LOBBY|IN_BATTLE → CANCELLED`. А также для обновления
        `current_boss_length_cm` / `current_round` после раунда.
        Для несуществующего `id` бросает `IntegrityError` (доменная —
        из `pipirik_wars.shared.errors`).
        """


class IBossParticipantRepository(abc.ABC):
    """Доступ к таблице `boss_participants` (ассоциативная)."""

    @abc.abstractmethod
    async def add(self, participant: BossParticipant) -> BossParticipant:
        """Добавить нового рейдера в рейд-бой.

        БД-ограничение `UNIQUE (boss_fight_id, player_id)` гарантирует,
        что игрок не вступит дважды в один рейд. Дубликат —
        `IntegrityError`.

        БД-ограничение `UNIQUE (boss_fight_id) WHERE is_summoner=true`
        гарантирует, что у одного боя максимум один саммонер.
        Дубликат — `IntegrityError`.
        """

    @abc.abstractmethod
    async def list_by_boss_fight(self, *, boss_fight_id: int) -> tuple[BossParticipant, ...]:
        """Список всех рейдеров рейд-боя в порядке `joined_at`.

        Используется `RunBossRound` / `FinishBossFight` (3.3-C) для
        resolve-а раундов и расчёта наград, и bot-handler-ом (3.3-D)
        для отображения лобби и итоговой карточки.
        """

    @abc.abstractmethod
    async def get_by_boss_fight_and_player(
        self, *, boss_fight_id: int, player_id: int
    ) -> BossParticipant | None:
        """Найти конкретного рейдера в рейде, либо `None`.

        Используется `LeaveBossLobby` / `RunBossRound` (3.3-B/C) для
        проверки, что игрок действительно участвует, прежде чем
        применять операцию.
        """

    @abc.abstractmethod
    async def remove(self, *, boss_fight_id: int, player_id: int) -> None:
        """Удалить рейдера (например, при `LeaveBossLobby`).

        No-op, если запись не существует. Для саммонера операция должна
        каскадировать в `BossFight.mark_cancelled` (если других рейдеров
        нет) — это логика use-case, не репозитория.
        """


__all__ = [
    "IBossFightRepository",
    "IBossParticipantRepository",
]
