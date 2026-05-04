"""Порты репозиториев `forest`.

`IForestRunRepository` отвечает за `forest_runs`: создание новой записи
со статусом `IN_PROGRESS`, поиск активного похода игрока (для проверки
«уже в лесу» из `StartForestRun`), и пометка финиша (`FinishForestRun`,
Спринт 1.3.C).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2).
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.forest.run import ForestRun


class IForestRunRepository(abc.ABC):
    """Доступ к таблице `forest_runs`."""

    @abc.abstractmethod
    async def add(self, run: ForestRun) -> ForestRun:
        """Добавить новый поход (`status=IN_PROGRESS`).

        На вход — `run.id is None`. Возвращает копию с проставленным `id`.
        """

    @abc.abstractmethod
    async def get_by_id(self, *, run_id: int) -> ForestRun | None:
        """Найти поход по `id`, либо `None`.

        Используется `FinishForestRun` (1.3.C) при срабатывании
        APScheduler-job-а: job передаёт `run_id`, use-case подтягивает
        запись и применяет исход.
        """

    @abc.abstractmethod
    async def get_active_by_player(self, *, player_id: int) -> ForestRun | None:
        """Найти активный (`IN_PROGRESS`) поход игрока, либо `None`.

        Гарантии: одновременно у одного игрока может быть **не более
        одного** `IN_PROGRESS` похода (это охраняется и activity_lock-ом
        на уровне use-case, и БД-инвариантом — см. миграцию 0004).
        """

    @abc.abstractmethod
    async def save(self, run: ForestRun) -> ForestRun:
        """Обновить запись по `id`.

        Используется `FinishForestRun` (1.3.C) для перевода
        `IN_PROGRESS → FINISHED`. Для несуществующего `id` бросает
        `IntegrityError` (доменная — из `pipirik_wars.shared.errors`).
        """
