"""Порты репозитория `mountains`.

`IMountainRunRepository` отвечает за `mountain_runs`: создание новой
записи со статусом `IN_PROGRESS`, поиск активного похода игрока (для
проверки «уже в горах» из `StartMountainRun`), и пометку финиша
(`FinishMountainRun`, Спринт 3.1-B).

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2).
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.mountains.entities import MountainRun


class IMountainRunRepository(abc.ABC):
    """Доступ к таблице `mountain_runs`."""

    @abc.abstractmethod
    async def add(self, run: MountainRun) -> MountainRun:
        """Добавить новый поход (`status=IN_PROGRESS`).

        На вход — `run.id is None`. Возвращает копию с проставленным `id`.
        """

    @abc.abstractmethod
    async def get_by_id(self, *, run_id: int) -> MountainRun | None:
        """Найти поход по `id`, либо `None`.

        Используется `FinishMountainRun` (3.1-B) при срабатывании
        APScheduler-job-а: job передаёт `run_id`, use-case подтягивает
        запись и применяет исход.
        """

    @abc.abstractmethod
    async def get_active_by_player(self, *, player_id: int) -> MountainRun | None:
        """Найти активный (`IN_PROGRESS`) поход игрока, либо `None`.

        Гарантии: одновременно у одного игрока может быть **не более
        одного** `IN_PROGRESS` похода в горы (охраняется и activity_lock-ом
        на уровне use-case, и БД-инвариантом — миграция в 3.1-B).
        """

    @abc.abstractmethod
    async def save(self, run: MountainRun) -> MountainRun:
        """Обновить запись по `id`.

        Используется `FinishMountainRun` (3.1-B) для перевода
        `IN_PROGRESS → FINISHED`. Для несуществующего `id` бросает
        `IntegrityError` (доменная — из `pipirik_wars.shared.errors`).
        """


__all__ = ["IMountainRunRepository"]
