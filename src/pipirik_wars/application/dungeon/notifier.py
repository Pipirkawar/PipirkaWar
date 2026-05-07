"""Порт нотификации финиша похода в данжон (Спринт 3.1-E, ГДД §8.2).

Зеркалит `IMountainFinishNotifier`. См. соседний модуль `mountains/notifier.py`
для развёрнутого обоснования (отдельный порт = best-effort I/O вне
транзакции, см. ГДД §0.3).
"""

from __future__ import annotations

import abc

from pipirik_wars.application.dungeon.finish_run import DungeonRunFinished


class IDungeonFinishNotifier(abc.ABC):
    """Контракт «прислать игроку сообщение о возвращении из данжона»."""

    @abc.abstractmethod
    async def notify(self, result: DungeonRunFinished) -> None:
        """Отправить сообщение «вернулся из данжона» (ГДД §8.2)."""


__all__ = ["IDungeonFinishNotifier"]
