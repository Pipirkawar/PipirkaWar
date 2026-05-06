"""Порт репозитория реферальной системы (Спринт 2.4.A)."""

from __future__ import annotations

import abc
from datetime import datetime

from pipirik_wars.domain.referral.entities import Referral


class IReferralRepository(abc.ABC):
    """Доступ к таблице `referrals`.

    Все методы исполняются внутри активного `IUnitOfWork`; собственный
    коммит репозиторий не делает (правило Спринта 0.2).
    """

    @abc.abstractmethod
    async def add(self, referral: Referral) -> Referral:
        """Добавить новую реферальную запись. Возвращает копию с проставленным `id`.

        При попытке добавить дубль на тот же `referred_id` репо обязан
        бросить `ReferralAlreadyExistsError`. На уровне БД UNIQUE-индекс
        на колонке `referred_id` ловит race; SQL-реализация конвертирует
        `IntegrityError` SQLAlchemy в доменную ошибку.
        """

    @abc.abstractmethod
    async def get_by_referred_id(self, referred_id: int) -> Referral | None:
        """Найти реферальную запись по приглашённому игроку.

        UNIQUE-индекс на `referred_id` гарантирует, что вернётся
        максимум одна запись. None — если игрок не был рефнут.
        """

    @abc.abstractmethod
    async def mark_signup_granted(
        self,
        *,
        referred_id: int,
        granted_at: datetime,
    ) -> Referral:
        """Атомарно проставить `signup_granted_at` для реферальной записи.

        Возвращает обновлённую запись. Если записи не существует —
        бросает `ReferralNotFoundError` (TBD; пока KeyError-стиль).
        Идемпотентно повторное проставление: вторая запись просто
        перезатирает время на новое (этот случай должен быть
        перехвачен на уровне use-case-а через
        `SignupBonusAlreadyGrantedError`).
        """

    @abc.abstractmethod
    async def mark_milestone_granted(
        self,
        *,
        referred_id: int,
        thickness: int,
    ) -> Referral:
        """Атомарно обновить `last_milestone_thickness` для реферальной записи.

        Поднимает значение колонки до `thickness` (`SET ... = GREATEST(
        last_milestone_thickness, :thickness)`). Возвращает обновлённую
        запись. Use-case проверяет `last_milestone_thickness < thickness`
        перед вызовом — если уже >= — бросает
        `MilestoneAlreadyGrantedError`.
        """


__all__ = ["IReferralRepository"]
