"""Доменные ошибки PvP (ГДД §7.1).

Иерархия:

* `PvpError` — общий root.
* `InvalidRoundCountError` — в `resolve_duel(...)` подали список с количеством
  раундов, отличным от ожидаемого (по умолчанию — 3 из ГДД §7.1).
* `InvalidLengthError` — `p1_length_cm` или `p2_length_cm` отрицательные либо
  ниже минимально-допустимого порога (валидируется в use-case-е, не в чистом
  движке; здесь — общая ошибка для будущих сценариев).
* `InvalidDuelStateError` — операция на агрегате `Duel` из неподходящего
  состояния (например, `submit_move` в `PENDING_ACCEPT`). Спринт 2.1.B.
* `MoveAlreadySubmittedError` — игрок уже отправил выбор на текущий раунд
  (повторный `submit_move`). Спринт 2.1.B.
* `NotADuelParticipantError` — `player_id` не является ни челленджером,
  ни оппонентом. Спринт 2.1.B.
* `SelfChallengeError` — `challenger_id == challenged_id` при создании
  вызова. Спринт 2.1.B.
* `NoMissingMovesError` — `force_complete_round` вызван, когда оба
  выбора уже отправлены (нечего фоллбэчить). Спринт 2.1.B.

Все ошибки — `domain`-слой и не зависят от инфраструктуры.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError

__all__ = [
    "InvalidDuelStateError",
    "InvalidLengthError",
    "InvalidRoundCountError",
    "MoveAlreadySubmittedError",
    "NoMissingMovesError",
    "NotADuelParticipantError",
    "PvpError",
    "SelfChallengeError",
]


class PvpError(DomainError):
    """Базовая ошибка PvP-домена."""


class InvalidRoundCountError(PvpError):
    """Подан список раундов с неожиданным `len(...)`.

    ГДД §7.1: бой 1×1 — ровно 3 раунда. Любая дельта (0, 1, 2, 4+) — баг
    выше доменного слоя (gather-loop собрал не все ходы, AFK-таймер
    отстрелил лишний и т. п.) и в чистом движке — невалидное состояние.
    """

    def __init__(self, *, expected: int, got: int) -> None:
        super().__init__(f"PvP duel expects exactly {expected} round(s), got {got}")
        self.expected = expected
        self.got = got


class InvalidLengthError(PvpError):
    """Длина игрока в момент входа в бой — не валидная (отрицательная).

    Минимальный порог 20 см проверяется на use-case-уровне; здесь —
    только защита от отрицательных значений, чтобы `damage = length * pct`
    не уехало в минус.
    """

    def __init__(self, *, side: str, length_cm: int) -> None:
        super().__init__(f"PvP {side} length must be >= 0 cm, got {length_cm} cm")
        self.side = side
        self.length_cm = length_cm


class InvalidDuelStateError(PvpError):
    """Операция запрошена на агрегате `Duel` из неподходящего состояния.

    Например, `submit_move` в `PENDING_ACCEPT` или `cancel` после
    `COMPLETED`. Use-case 2.1.D/E конвертит ошибку в локализованное
    сообщение игроку («бой ещё не начался» / «бой уже завершён»).
    """

    def __init__(self, *, expected: object, actual: object, op: str) -> None:
        super().__init__(
            f"PvP duel op '{op}' requires state {expected}, but state is {actual}",
        )
        self.expected = expected
        self.actual = actual
        self.op = op


class NotADuelParticipantError(PvpError):
    """`player_id` не является ни челленджером, ни оппонентом.

    Возникает при попытке принять чужой вызов или отправить ход за
    игрока, который не участвует в этом бою. Use-case конвертит в
    «вы не участник этого боя».
    """

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player {player_id} is not a participant of this duel")
        self.player_id = player_id


class SelfChallengeError(PvpError):
    """`challenger_id == challenged_id` при создании вызова.

    Игрок не может бросить вызов сам себе. Use-case конвертит в
    «нельзя вызвать самого себя».
    """

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"player {player_id} cannot challenge themselves")
        self.player_id = player_id


class MoveAlreadySubmittedError(PvpError):
    """Повторный `submit_move` от игрока, у которого выбор на текущем
    раунде уже зафиксирован.

    Use-case конвертит в локализованное «вы уже выбрали в этом раунде».
    """

    def __init__(self, *, player_id: int, round_num: int) -> None:
        super().__init__(
            f"player {player_id} already submitted a move for round {round_num}",
        )
        self.player_id = player_id
        self.round_num = round_num


class NoMissingMovesError(PvpError):
    """`force_complete_round` вызван, когда оба выбора уже отправлены —
    AFK-фоллбэчить нечего.

    Сигнал багу в use-case-е 2.1.E (раунд-таймер сработал после того,
    как оба игрока уже выбрали).
    """

    def __init__(self, *, round_num: int) -> None:
        super().__init__(
            f"round {round_num} has no missing moves to force-complete",
        )
        self.round_num = round_num
