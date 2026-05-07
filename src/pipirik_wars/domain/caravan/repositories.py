"""Порты репозиториев домена «Караван» (Спринт 3.2-A, ГДД §9).

Два порта:

- `ICaravanRepository` — CRUD для агрегата `Caravan`.
- `ICaravanParticipantRepository` — CRUD + listing для
  `CaravanParticipant` (ассоциативная таблица).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозитории не делают (правило Спринта 0.2).

Реализации — Спринт 3.2-B (SQLAlchemy + миграция `0019_caravans`).
"""

from __future__ import annotations

import abc
from datetime import datetime

from pipirik_wars.domain.caravan.entities import Caravan, CaravanParticipant
from pipirik_wars.domain.caravan.value_objects import CaravanRole


class ICaravanRepository(abc.ABC):
    """Доступ к таблице `caravans` (агрегат `Caravan`)."""

    @abc.abstractmethod
    async def add(self, caravan: Caravan) -> Caravan:
        """Добавить новый караван (`status=LOBBY`).

        На вход — `caravan.id is None`. Возвращает копию с проставленным `id`.
        """

    @abc.abstractmethod
    async def get_by_id(self, *, caravan_id: int) -> Caravan | None:
        """Найти караван по `id`, либо `None`."""

    @abc.abstractmethod
    async def get_active_by_clan(self, *, clan_id: int) -> Caravan | None:
        """Найти активный караван клана-отправителя, либо `None`.

        Активный = `status in (LOBBY, IN_BATTLE)`. Гарантия: одновременно
        у одного клана может быть **не более одного** активного каравана
        (БД-инвариант через `UNIQUE INDEX` partial WHERE; миграция 3.2-B).
        """

    @abc.abstractmethod
    async def get_last_finished_at_for_clan(self, *, clan_id: int) -> datetime | None:
        """Время последнего перехода `LOBBY → IN_BATTLE`/`CANCELLED` клана.

        Используется `CreateCaravan` (3.2-B) для проверки 12-часового
        кулдауна (ГДД §9.3). Возвращает `None`, если у клана ещё не
        было ни одного каравана.

        ВАЖНО (по решению на старте 3.2): кулдаун начинается с
        `started_at` создания каравана, не с `finished_at`. То есть
        `last_finished_at_for_clan` — на самом деле «время последнего
        `started_at`». Имя сохранено для совместимости с шаблоном
        forest/PvE; в Спринте 3.2-B уточним в реализации.
        """

    @abc.abstractmethod
    async def save(self, caravan: Caravan) -> Caravan:
        """Обновить запись каравана по `id`.

        Используется в 3.2-B/C для переходов:
        `LOBBY → IN_BATTLE`, `IN_BATTLE → FINISHED`,
        `LOBBY|IN_BATTLE → CANCELLED`. Для несуществующего `id` бросает
        `IntegrityError` (доменная — из `pipirik_wars.shared.errors`).
        """


class ICaravanParticipantRepository(abc.ABC):
    """Доступ к таблице `caravan_participants` (ассоциативная)."""

    @abc.abstractmethod
    async def add(self, participant: CaravanParticipant) -> CaravanParticipant:
        """Добавить нового участника каравана.

        БД-ограничение `UNIQUE (caravan_id, player_id)` гарантирует,
        что игрок не вступит дважды в один караван с разных ролей.
        Дубликат — `IntegrityError`.
        """

    @abc.abstractmethod
    async def list_by_caravan(self, *, caravan_id: int) -> tuple[CaravanParticipant, ...]:
        """Список всех участников каравана в порядке `joined_at`.

        Используется `FinishCaravanBattle` (3.2-C) для resolve-а боя и
        bot-handler-ом (3.2-D) для отображения лобби и итоговой
        карточки.
        """

    @abc.abstractmethod
    async def list_by_caravan_and_role(
        self, *, caravan_id: int, role: CaravanRole
    ) -> tuple[CaravanParticipant, ...]:
        """Подмножество участников по роли (например, все `RAIDER`-ы).

        Используется capacity-чекером в `JoinCaravanLobby` (3.2-B):
        проверка предела `RAIDER` ≤ ×4 от `CARAVANEER` и
        `DEFENDER` ≤ ×2.
        """

    @abc.abstractmethod
    async def remove(self, *, caravan_id: int, player_id: int) -> None:
        """Удалить участника (например, при `LeaveCaravanLobby`).

        No-op, если запись не существует. Изменение баланса (возврат
        `contribution_cm` в длину игрока) — на уровне use-case.
        """


__all__ = [
    "ICaravanParticipantRepository",
    "ICaravanRepository",
]
