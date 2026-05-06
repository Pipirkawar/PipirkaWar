"""Доменные ошибки реферальной системы (ГДД §13.1, Спринт 2.4)."""

from __future__ import annotations


class ReferralError(Exception):
    """Базовый класс ошибок реферальной системы."""


class SelfReferralError(ReferralError):
    """Игрок не может пригласить сам себя.

    Бросается при попытке создать `Referral` с `referrer_id == referred_id`.
    Также проверяется на уровне use-case-а до создания записи.
    """

    def __init__(self, *, player_id: int) -> None:
        super().__init__(f"Self-referral attempt by player_id={player_id}")
        self.player_id = player_id


class ReferralAlreadyExistsError(ReferralError):
    """Игрок уже был приглашён ранее.

    Бросается репозиторием при попытке `add()` дубля по `referred_id`
    (UNIQUE-индекс на колонке). Use-case `RegisterReferral` ловит её
    и возвращает «no-op» — реферирование одного и того же игрока
    повторно не пересоздаёт связь и не начисляет бонусов.
    """

    def __init__(self, *, referred_id: int) -> None:
        super().__init__(f"Referral for referred_id={referred_id} already exists")
        self.referred_id = referred_id


class ReferrerNotRegisteredError(ReferralError):
    """Реферер не зарегистрирован в `players`.

    Бросается use-case-ом `RegisterReferral`, если по `referrer_tg_id`
    из `start=ref_<id>` не нашёлся ни один player. Handler конвертирует
    в тихий no-op (нельзя стать реферером, не будучи зарегистрированным).
    """

    def __init__(self, *, referrer_tg_id: int) -> None:
        super().__init__(f"Referrer with tg_id={referrer_tg_id} is not registered")
        self.referrer_tg_id = referrer_tg_id


class SignupBonusAlreadyGrantedError(ReferralError):
    """Signup-бонус по этой реферальной записи уже был выдан.

    Бросается use-case-ом `GrantReferralSignupBonus`, если запись
    `Referral.signup_granted_at is not None`. На handler-уровне это
    no-op (повторный вызов из re-delivery не должен начислять бонус
    второй раз).
    """

    def __init__(self, *, referred_id: int) -> None:
        super().__init__(f"Signup bonus for referred_id={referred_id} already granted")
        self.referred_id = referred_id


class MilestoneAlreadyGrantedError(ReferralError):
    """Milestone по этой толщине уже был выдан.

    Бросается use-case-ом `GrantReferralThicknessMilestone`, если
    `last_milestone_thickness >= thickness`. Игрок не получает бонус
    за повторное достижение того же уровня (если уровень понижен и
    повышен снова). Это no-op на handler-уровне.
    """

    def __init__(self, *, referred_id: int, thickness: int) -> None:
        super().__init__(
            f"Milestone for referred_id={referred_id}, thickness={thickness} already granted"
        )
        self.referred_id = referred_id
        self.thickness = thickness


__all__ = [
    "MilestoneAlreadyGrantedError",
    "ReferralAlreadyExistsError",
    "ReferralError",
    "ReferrerNotRegisteredError",
    "SelfReferralError",
    "SignupBonusAlreadyGrantedError",
]
