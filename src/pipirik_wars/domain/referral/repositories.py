"""Порт репозитория реферальной системы (Спринт 2.4.A)."""

from __future__ import annotations

import abc
from collections.abc import Sequence
from datetime import datetime

from pipirik_wars.domain.referral.entities import Referral, WeeklyClanReferralEntry


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

    @abc.abstractmethod
    async def weekly_summary_by_clan(
        self,
        *,
        clan_id: int,
        since: datetime,
        until: datetime,
    ) -> Sequence[WeeklyClanReferralEntry]:
        """Сколько новых рефералов привёл каждый член клана за окно `[since, until)`.

        Группировка `referrals.referrer_id` → `count(referrals.id)` среди
        тех `referrer_id`, которые состоят в `clan_members(clan_id=:cid)`.
        Реферал (приглашённый игрок) НЕ обязан быть в клане — еженедельная
        карточка показывает рост клана через активность его участников
        (ГДД §13.1: реферальный приз идёт пригласившему).

        Окно полузакрытое: `created_at >= since AND created_at < until`.
        Реализациям следует:

        - возвращать только записи с `count > 0` (отсутствие реферера в
          списке = «никого не пригласил за окно»);
        - стабильный порядок: `count DESC, referrer_id ASC` — это то,
          что увидит пользователь в финальной карточке (top-3); тестам
          нужен детерминизм.

        Use-case `RunWeeklyClanReferralSummary` (Спринт 2.4.E) дальше
        резолвит `referrer_id` → `Player` и достаёт top-3 для текста
        weekly-карточки (`weekly-referral-summary-*`).

        :raises ValueError: если `since >= until` (защита от пустого / инверсного окна).
        """


__all__ = ["IReferralRepository"]
