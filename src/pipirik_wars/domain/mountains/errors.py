"""Domain-ошибки гор."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class MountainError(DomainError):
    """Базовая ошибка гор."""


class AlreadyInMountainsError(MountainError):
    """Игрок уже в активном походе в горы.

    Бросает `StartMountainRun` (Спринт 3.1-B), когда `activity_lock`
    на `(player, MOUNTAINS)` уже взят.
    """

    __slots__ = ("player_id",)

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already in a mountain run")
        self.player_id = player_id


class MountainRunNotFoundError(MountainError):
    """`mountain_runs` не содержит записи с таким `id`.

    Бросает `FinishMountainRun`, когда APScheduler-job стрельнул на
    несуществующий `run_id` (ручное удаление, рассинхрон между БД
    и job-store).
    """

    __slots__ = ("run_id",)

    def __init__(self, *, run_id: int) -> None:
        super().__init__(f"mountain_run id={run_id} not found")
        self.run_id = run_id


class MountainRunOwnershipError(MountainError):
    """Игрок пытается применить исход чужого похода.

    Защита от подмены `callback_data`: id игрока, нажавшего кнопку,
    обязан совпасть с `mountain_runs.player_id`.
    """

    __slots__ = ("actor_player_id", "run_id", "run_player_id")

    def __init__(self, *, run_id: int, run_player_id: int, actor_player_id: int) -> None:
        super().__init__(
            f"mountain_run id={run_id} belongs to player_id={run_player_id}, "
            f"got actor player_id={actor_player_id}"
        )
        self.run_id = run_id
        self.run_player_id = run_player_id
        self.actor_player_id = actor_player_id


class MountainsRequirementError(MountainError):
    """Игрок не соответствует требованиям ГДД §8 для входа в горы.

    Минимальный уровень толщины (`thickness.unlock_levels.mountains = 3`)
    и минимальная длина (`pve.min_length_cm = 20`). Конкретное поле,
    которое не прошло, передаётся в `requirement` (`thickness` / `length`).

    Бросает `StartMountainRun` (Спринт 3.1-B); handler в Спринте 3.1-E
    маппит на локализованное сообщение игроку.
    """

    __slots__ = ("actual", "player_id", "required", "requirement")

    def __init__(
        self,
        *,
        player_id: int,
        requirement: str,
        required: int,
        actual: int,
    ) -> None:
        super().__init__(
            f"player_id={player_id} fails mountains requirement {requirement!r}: "
            f"required>={required}, got {actual}"
        )
        self.player_id = player_id
        self.requirement = requirement
        self.required = required
        self.actual = actual


__all__ = [
    "AlreadyInMountainsError",
    "MountainError",
    "MountainRunNotFoundError",
    "MountainRunOwnershipError",
    "MountainsRequirementError",
]
