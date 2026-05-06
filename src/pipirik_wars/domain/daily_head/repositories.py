"""Порты репозиториев «Главы клана дня» (Спринт 2.3.A).

Два независимых порта:

- `IDailyHeadRepository` — таблица `daily_heads` (само назначение,
  суточный кулдаун, история).
- `IDailyActivityRepository` — таблица `daily_active` (агрегатное
  представление «кто из клана активен за последние N дней» —
  достаточно поля `last_active_at` per-player + JOIN на `clan_members`,
  но порт скрывает источник: реализация может строить активность
  по аудит-логу, по `players.last_seen_at`, и т.п.).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2).
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from datetime import date

from pipirik_wars.domain.daily_head.entities import DailyHeadAssignment


class IDailyHeadRepository(abc.ABC):
    """Доступ к таблице `daily_heads`."""

    @abc.abstractmethod
    async def get_by_clan_and_date(
        self,
        *,
        clan_id: int,
        moscow_date: date,
    ) -> DailyHeadAssignment | None:
        """Найти назначение на `(clan_id, moscow_date)`. None — если не было.

        UNIQUE-индекс по `(clan_id, moscow_date)` гарантирует, что
        возвратится максимум одна запись.
        """

    @abc.abstractmethod
    async def add(self, assignment: DailyHeadAssignment) -> DailyHeadAssignment:
        """Добавить новое назначение. Возвращает копию с проставленным `id`.

        При попытке добавить дубль на тот же `(clan_id, moscow_date)`
        репо обязан бросить `DailyHeadAlreadyAssignedError`. На уровне
        БД UNIQUE-индекс ловит race; SQL-реализация конвертирует
        `IntegrityError` SQLAlchemy в доменную ошибку. Use-case 2.3.C
        перехватывает её и делает повторный `get_by_clan_and_date(...)`,
        возвращая запись победителя гонки.
        """

    @abc.abstractmethod
    async def list_recent_for_clan(
        self,
        *,
        clan_id: int,
        limit: int,
    ) -> Sequence[DailyHeadAssignment]:
        """Последние `limit` назначений главы для клана.

        Используется доменным `DailyHeadService` для anti-repeat-фильтра
        `avoid_last_n` (по умолчанию 3): из пула «активных» игроков
        исключаются те, кто уже был главой в последние N назначений.

        Контракт реализаций:
        - возвращает не более `limit` элементов;
        - порядок — `assigned_at DESC, id DESC` (свежие первыми);
        - тай-брейкер `id DESC` обязателен — `assigned_at` приходит
          из `IClock` и в тестах часто совпадает у соседних записей.
        """


class IDailyActivityRepository(abc.ABC):
    """Доступ к «активности участников клана за последние N дней»."""

    @abc.abstractmethod
    async def list_active_member_ids(
        self,
        *,
        clan_id: int,
        within_days: int,
    ) -> Sequence[int]:
        """ID-ы активных за последние `within_days` суток участников клана.

        «Активный» = есть хотя бы одна запись активности (определяется
        реализацией: `players.last_seen_at`, `audit_log` за период,
        и т.п.) в окне `[now - within_days, now]`. Игроки в статусе
        `FROZEN` исключаются автоматически.

        Контракт реализаций:
        - возвращает только `player_id`, входящие в `clan_members`
          этого клана;
        - заморозкенные / удалённые из клана игроки исключаются;
        - порядок не гарантирован (вызывающий код применяет свой
          фильтр + `IRandom.choice`).
        """
