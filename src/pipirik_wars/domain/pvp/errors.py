"""Доменные ошибки PvP (ГДД §7.1).

Иерархия:

* `PvpError` — общий root.
* `InvalidRoundCountError` — в `resolve_duel(...)` подали список с количеством
  раундов, отличным от ожидаемого (по умолчанию — 3 из ГДД §7.1).
* `InvalidLengthError` — `p1_length_cm` или `p2_length_cm` отрицательные либо
  ниже минимально-допустимого порога (валидируется в use-case-е, не в чистом
  движке; здесь — общая ошибка для будущих сценариев).

Все ошибки — `domain`-слой и не зависят от инфраструктуры.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError

__all__ = [
    "InvalidLengthError",
    "InvalidRoundCountError",
    "PvpError",
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
