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


class ForestRunNotFoundError(ForestError):
    """`forest_runs` не содержит записи с таким `id`.

    Бросает `FinishForestRun`, когда APScheduler-job стрельнул на
    несуществующий `run_id` (ручное удаление, рассинхрон между БД
    и job-store). Handler в Спринте 1.3.D логирует ошибку и не
    отправляет сообщение игроку.
    """

    __slots__ = ("run_id",)

    def __init__(self, *, run_id: int) -> None:
        super().__init__(f"forest_run id={run_id} not found")
        self.run_id = run_id
