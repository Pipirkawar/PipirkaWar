"""Domain-ошибки данжона."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class DungeonError(DomainError):
    """Базовая ошибка данжона."""


class AlreadyInDungeonError(DungeonError):
    """Игрок уже в активном походе в данжон.

    Бросает `StartDungeonRun` (Спринт 3.1-B), когда `activity_lock`
    на `(player, DUNGEON)` уже взят.
    """

    __slots__ = ("player_id",)

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player_id={player_id} is already in a dungeon run")
        self.player_id = player_id


class DungeonRunNotFoundError(DungeonError):
    """`dungeon_runs` не содержит записи с таким `id`.

    Бросает `FinishDungeonRun`, когда APScheduler-job стрельнул на
    несуществующий `run_id`.
    """

    __slots__ = ("run_id",)

    def __init__(self, *, run_id: int) -> None:
        super().__init__(f"dungeon_run id={run_id} not found")
        self.run_id = run_id


class DungeonRunOwnershipError(DungeonError):
    """Игрок пытается применить исход чужого похода.

    Защита от подмены `callback_data`: id игрока, нажавшего кнопку,
    обязан совпасть с `dungeon_runs.player_id`.
    """

    __slots__ = ("actor_player_id", "run_id", "run_player_id")

    def __init__(self, *, run_id: int, run_player_id: int, actor_player_id: int) -> None:
        super().__init__(
            f"dungeon_run id={run_id} belongs to player_id={run_player_id}, "
            f"got actor player_id={actor_player_id}"
        )
        self.run_id = run_id
        self.run_player_id = run_player_id
        self.actor_player_id = actor_player_id


class DungeonRequirementError(DungeonError):
    """Игрок не соответствует требованиям ГДД §8 для входа в данжон.

    Минимальный уровень толщины (`thickness.unlock_levels.dungeon = 6`)
    и минимальная длина (`pve.min_length_cm = 20`). Конкретное поле,
    которое не прошло, передаётся в `requirement` (`thickness` / `length`).
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
            f"player_id={player_id} fails dungeon requirement {requirement!r}: "
            f"required>={required}, got {actual}"
        )
        self.player_id = player_id
        self.requirement = requirement
        self.required = required
        self.actual = actual


__all__ = [
    "AlreadyInDungeonError",
    "DungeonError",
    "DungeonRequirementError",
    "DungeonRunNotFoundError",
    "DungeonRunOwnershipError",
]
