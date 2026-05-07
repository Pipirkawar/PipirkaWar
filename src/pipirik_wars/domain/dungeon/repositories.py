"""Порты репозитория `dungeon`.

`IDungeonRunRepository` отвечает за `dungeon_runs`: создание новой
записи со статусом `IN_PROGRESS`, поиск активного похода игрока,
и пометку финиша (`FinishDungeonRun`, Спринт 3.1-B).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2).
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.dungeon.entities import DungeonRun


class IDungeonRunRepository(abc.ABC):
    """Доступ к таблице `dungeon_runs`."""

    @abc.abstractmethod
    async def add(self, run: DungeonRun) -> DungeonRun:
        """Добавить новый поход (`status=IN_PROGRESS`).

        На вход — `run.id is None`. Возвращает копию с проставленным `id`.
        """

    @abc.abstractmethod
    async def get_by_id(self, *, run_id: int) -> DungeonRun | None:
        """Найти поход по `id`, либо `None`."""

    @abc.abstractmethod
    async def get_active_by_player(self, *, player_id: int) -> DungeonRun | None:
        """Найти активный (`IN_PROGRESS`) поход игрока, либо `None`.

        Гарантии: одновременно у одного игрока может быть **не более
        одного** `IN_PROGRESS` похода в данжон (охраняется и activity_lock-ом
        на уровне use-case, и БД-инвариантом — миграция в 3.1-B).
        """

    @abc.abstractmethod
    async def save(self, run: DungeonRun) -> DungeonRun:
        """Обновить запись по `id`.

        Используется `FinishDungeonRun` (3.1-B) для перевода
        `IN_PROGRESS → FINISHED`. Для несуществующего `id` бросает
        `IntegrityError` (доменная — из `pipirik_wars.shared.errors`).
        """


__all__ = ["IDungeonRunRepository"]
