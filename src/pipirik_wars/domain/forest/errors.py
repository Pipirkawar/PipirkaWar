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


class ForestRunOwnershipError(ForestError):
    """Игрок пытается применить дроп чужого похода.

    Защита от подмены `callback_data`: id игрока, нажавшего кнопку,
    обязан совпасть с `forest_runs.player_id`. Иначе use-case
    `ApplyForestNameDrop` (Спринт 1.3.D) бросает эту ошибку, и handler
    логирует попытку без раскрытия деталей пользователю.
    """

    __slots__ = ("actor_player_id", "run_id", "run_player_id")

    def __init__(self, *, run_id: int, run_player_id: int, actor_player_id: int) -> None:
        super().__init__(
            f"forest_run id={run_id} belongs to player_id={run_player_id}, "
            f"got actor player_id={actor_player_id}"
        )
        self.run_id = run_id
        self.run_player_id = run_player_id
        self.actor_player_id = actor_player_id


class ForestDropMismatchError(ForestError):
    """Тип дропа не соответствует ожидаемому действием use-case-а.

    Например, `ApplyForestNameDrop` дернули на запись с `ItemDrop` или
    `NoDrop`. Handler не должен такое строить — это защита для случая,
    если callback_data «забалансирована» (например, после регенерации
    кнопок при будущих изменениях формата).
    """

    __slots__ = ("expected", "got", "run_id")

    def __init__(self, *, run_id: int, expected: str, got: str) -> None:
        super().__init__(
            f"forest_run id={run_id} drop kind mismatch: expected={expected!r}, got={got!r}"
        )
        self.run_id = run_id
        self.expected = expected
        self.got = got
