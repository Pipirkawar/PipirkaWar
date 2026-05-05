"""Порты репозиториев PvP-подсистемы (Спринт 2.1.C).

`IDuelRepository` — доступ к таблице `pvp_duels` (+ `pvp_duel_rounds`
для completed-раундов). Сериализует поле-в-поле агрегат `Duel`
из домена 2.1.B.

Все методы исполняются внутри активного `IUnitOfWork`; собственный
коммит репозиторий не делает (правило Спринта 0.2). Use-case-ы 2.1.D
вызывают `add(...)` / `save(...)` через ambient-UoW.
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.pvp.duel import Duel


class IDuelRepository(abc.ABC):
    """Доступ к таблице `pvp_duels` (через `pvp_duel_rounds` для completed-раундов)."""

    @abc.abstractmethod
    async def add(self, duel: Duel) -> Duel:
        """Добавить новый duel-агрегат.

        На вход — `duel.id is None`. Возвращает копию с проставленным
        `id` (PK из БД). Завершённые раунды (`completed_rounds`)
        записываются в `pvp_duel_rounds` через тот же `INSERT`.

        Бросает доменный `IntegrityError`, если БД-уровневые
        CHECK-/FK-инварианты нарушены (например, `challenger_id` не
        существует в `users`).
        """

    @abc.abstractmethod
    async def get_by_id(self, *, duel_id: int) -> Duel | None:
        """Найти duel по `id`, либо `None`.

        Загружает root-row из `pvp_duels` и все связанные
        completed-раунды из `pvp_duel_rounds` (в порядке `round_num`).
        """

    @abc.abstractmethod
    async def save(self, duel: Duel) -> Duel:
        """Обновить существующий duel-агрегат по `id`.

        На вход — `duel.id is not None`. Перезаписывает все поля
        root-row-а и синхронизирует `pvp_duel_rounds` (новые
        completed-раунды добавляются; уже существующие не трогаются —
        в домене round-record иммутабелен после авторазрешения).

        Бросает доменный `IntegrityError`, если запись с таким `id` не
        найдена или БД-уровневые инварианты нарушены.
        """
