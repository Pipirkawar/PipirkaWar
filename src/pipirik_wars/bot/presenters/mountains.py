"""Презентер `/mountains` (Спринт 3.1-E, ГДД §8.2).

Тонкая обёртка над `PvePresenter` с зашитым `PveLocationKind.MOUNTAINS`.
Используется handler-ом и нотификатором.
"""

from __future__ import annotations

from pipirik_wars.application.i18n import IMessageBundle
from pipirik_wars.bot.presenters._pve import PvePresenter
from pipirik_wars.domain.pve import PveLocationKind


class MountainsPresenter(PvePresenter):
    """`PvePresenter`, заведённый на `mountains`-префиксе локали."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        super().__init__(bundle=bundle, kind=PveLocationKind.MOUNTAINS)


__all__ = ["MountainsPresenter"]
