"""Ошибки подсистемы прогрессии."""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class InsufficientLengthError(DomainError):
    """Списание невозможно: после вычета останется < `min_after_spend_cm`.

    Бросается из `progression.require_spend(...)`. На уровне bot/admin
    маппится на дружелюбное сообщение «нужно ещё N см» (handler сам
    считает дельту по полям ошибки).

    Поля:
    - `length_cm` — текущая длина игрока (положительное число).
    - `cost_cm` — стоимость операции (положительное число).
    - `min_after_spend_cm` — порог, который должен остаться после
      списания (по ГДД §3.1 — `20`).
    - `action` — для какого действия проверка не прошла (для аудита
      и UX-сообщений).
    """

    __slots__ = ("action", "cost_cm", "length_cm", "min_after_spend_cm")

    def __init__(
        self,
        *,
        length_cm: int,
        cost_cm: int,
        min_after_spend_cm: int,
        action: str,
    ) -> None:
        remaining = length_cm - cost_cm
        super().__init__(
            f"insufficient length for {action!r}: "
            f"length={length_cm} cm, cost={cost_cm} cm, "
            f"remaining={remaining} cm < min_after_spend={min_after_spend_cm} cm",
        )
        self.length_cm = length_cm
        self.cost_cm = cost_cm
        self.min_after_spend_cm = min_after_spend_cm
        self.action = action

    @property
    def deficit_cm(self) -> int:
        """Сколько ещё см не хватает игроку, чтобы операция прошла.

        Всегда `> 0`. Удобно для UX-сообщения «нужно ещё N см».
        """
        deficit = self.min_after_spend_cm - (self.length_cm - self.cost_cm)
        return max(deficit, 1)


class ActivityLockedError(DomainError):
    """Активность заблокирована: текущая толщина ниже требуемой (ГДД §3.3).

    Бросается из `progression.require_unlocked(...)`. На уровне bot/admin
    маппится на сообщение «нужна толщина ≥ N для входа в активность».

    Поля:
    - `activity` — строковый ключ активности (ключ из `balance.yaml::thickness.unlock_levels`).
    - `current_thickness` — текущий уровень игрока (>= 1).
    - `required_thickness` — минимальный уровень для входа (>= 1).
    """

    __slots__ = ("activity", "current_thickness", "required_thickness")

    def __init__(
        self,
        *,
        activity: str,
        current_thickness: int,
        required_thickness: int,
    ) -> None:
        super().__init__(
            f"activity {activity!r} requires thickness >= {required_thickness}, "
            f"got {current_thickness}",
        )
        self.activity = activity
        self.current_thickness = current_thickness
        self.required_thickness = required_thickness
