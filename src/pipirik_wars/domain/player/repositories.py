"""Репозиторий игроков (порт)."""

from __future__ import annotations

import abc

from pipirik_wars.domain.player.entities import Player


class IPlayerRepository(abc.ABC):
    """Доступ к таблице `users`.

    Все методы исполняются внутри активной транзакции `IUnitOfWork`;
    собственный коммит репозиторий не делает (правило Спринта 0.2,
    единый источник коммита — UoW). При нарушении уникальности
    `tg_id` репозиторий бросает `PlayerAlreadyRegisteredError`.
    """

    @abc.abstractmethod
    async def get_by_tg_id(self, tg_id: int) -> Player | None:
        """Найти игрока по Telegram-ID или вернуть `None`."""

    @abc.abstractmethod
    async def get_by_id(self, *, player_id: int) -> Player | None:
        """Найти игрока по внутреннему `id`, либо вернуть `None`.

        Используется в use-case-ах, которые загружают игрока по
        `player_id`, а не по `tg_id` (например, `FinishForestRun`
        получает `player_id` из `forest_runs`).
        """

    @abc.abstractmethod
    async def add(self, player: Player) -> Player:
        """Добавить нового игрока. Возвращает копию с проставленным `id`.

        Для уже существующего `tg_id` бросает
        `PlayerAlreadyRegisteredError` (см. `domain.player.errors`).
        """

    @abc.abstractmethod
    async def save(self, player: Player) -> Player:
        """Обновить запись по `id`. Возвращает «канонический» инстанс,
        каким он лёг в БД (с обновлённым `updated_at`, если БД его
        перепишет server-side).

        Для несуществующего `id` бросает `IntegrityError`.
        """
