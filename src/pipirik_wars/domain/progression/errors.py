"""Ошибки подсистемы прогрессии."""

from __future__ import annotations

from datetime import datetime

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


class AnticheatSoftBanError(DomainError):
    """Игрок в активном soft-ban-е, прибавка длины запрещена (Спринт 1.6.D, ГДД §3.3.5).

    Бросается из `ILengthGranter.grant(...)` если на момент вызова
    `Player.is_anticheat_banned(now=clock.now())` вернул `True`. Все
    мутации откатываются (use-case даже не доходит до save). На уровне
    bot/handler маппится на локализованное сообщение
    `anticheat-soft-ban-active`.

    Поля:
    - `tg_id` — Telegram-id игрока (для логов).
    - `banned_until` — момент, до которого активен бан (UTC, tz-aware).
      Hander использует, чтобы показать «бан до DD.MM HH:MM UTC».
    """

    __slots__ = ("banned_until", "tg_id")

    def __init__(
        self,
        *,
        tg_id: int,
        banned_until: datetime,
    ) -> None:
        super().__init__(
            f"player tg_id={tg_id} is in anticheat soft-ban until {banned_until.isoformat()}",
        )
        self.tg_id = tg_id
        self.banned_until = banned_until


class LengthDeltaInvalidError(DomainError):
    """Дельта прибавки длины несовместима с указанным `source` (Спринт 1.6.D).

    Бросается из `ILengthGranter.grant(...)` при попытке передать:

    - `delta_cm = 0` — нет смысла в no-op-операции, симптом бага у caller-а;
    - отрицательную `delta_cm` для не-`admin_refund` источника;
    - положительную `delta_cm` для `admin_refund` (это сторно — должна
      быть отрицательной);
    - `source = AuditSource.UNKNOWN` — это backfill-маркер для записей
      до Спринта 1.6.A, а не реальный источник; новые `LENGTH_GRANT`-ы
      обязаны указывать конкретный enum-член.

    Поля:
    - `delta_cm` — переданная дельта.
    - `source` — переданный source (строкой, для логов).
    - `reason_code` — машинный код причины (для тестов и логов):
      `"zero"` / `"negative_for_non_refund"` / `"positive_for_refund"` /
      `"unknown_source"`.
    """

    __slots__ = ("delta_cm", "reason_code", "source")

    def __init__(
        self,
        *,
        delta_cm: int,
        source: str,
        reason_code: str,
    ) -> None:
        super().__init__(
            f"invalid delta_cm={delta_cm} for source={source!r}: {reason_code}",
        )
        self.delta_cm = delta_cm
        self.source = source
        self.reason_code = reason_code
