"""Domain-ошибки леса."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class ForestError(DomainError):
    """Базовая ошибка леса."""


class AlreadyInForestError(ForestError):
    """Игрок уже в активном походе.

    Бросает `StartForestRun`, когда `activity_lock` на `(player, FOREST)`
    уже взят. Handler в Спринте 1.3.D перехватывает её и показывает
    игроку сообщение «вы заняты, лес ещё не закончился» (ПД §1.3.9).
    """

    __slots__ = ("player_id",)

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already in a forest run")
        self.player_id = player_id
