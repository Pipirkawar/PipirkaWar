"""Презентер `/dungeon` (Спринт 3.1-E, ГДД §8.2).

Тонкая обёртка над `PvePresenter` с зашитым `PveLocationKind.DUNGEON`.
"""

from __future__ import annotations

from pipirik_wars.application.i18n import IMessageBundle
from pipirik_wars.bot.presenters._pve import PvePresenter
from pipirik_wars.domain.pve import PveLocationKind


class DungeonPresenter(PvePresenter):
    """`PvePresenter`, заведённый на `dungeon`-префиксе локали."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        super().__init__(bundle=bundle, kind=PveLocationKind.DUNGEON)


__all__ = ["DungeonPresenter"]
