"""Реализация `IReferralRepository` поверх таблицы `referrals` (Спринт 2.4.B)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.referral import (
    IReferralRepository,
    Referral,
    ReferralAlreadyExistsError,
)
from pipirik_wars.infrastructure.db.models import ReferralORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc


class _ReferralNotFoundError(KeyError):
    """Внутренняя ошибка репозитория: запись не найдена при mark_*-апдейте.

    Поднимается в `mark_signup_granted` / `mark_milestone_granted`, если
    `referred_id` не найден. Use-case-ам обычно не нужно её ловить, потому
    что они сначала делают `get_by_referred_id(...)`. Класс приватный,
    вне репозитория не нужен.
    """


def _row_to_entity(row: ReferralORM) -> Referral:
    """Маппит ORM-строку в доменный VO с tzinfo-восстановлением для SQLite."""
    return Referral(
        id=row.id,
        referrer_id=row.referrer_id,
        referred_id=row.referred_id,
        created_at=ensure_utc(row.created_at),
        signup_granted_at=(
            ensure_utc(row.signup_granted_at) if row.signup_granted_at is not None else None
        ),
        last_milestone_thickness=row.last_milestone_thickness,
    )


class SqlAlchemyReferralRepository(IReferralRepository):
    """Persistence-реализация `IReferralRepository` через UoW.

    UNIQUE-индекс на `referred_id` гарантирует «один игрок = одна
    реферальная запись». При гонке двух конкурентных INSERT-ов (двух
    разных `start=ref_<X>`+`start=ref_<Y>` для одного игрока,
    маловероятно но возможно) БД отбрасывает дубль `IntegrityError`,
    репозиторий конвертирует его в `ReferralAlreadyExistsError`.
    Use-case `RegisterReferral` ловит её и no-op-ит.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def add(self, referral: Referral) -> Referral:
        row = ReferralORM(
            referrer_id=referral.referrer_id,
            referred_id=referral.referred_id,
            created_at=referral.created_at,
            signup_granted_at=referral.signup_granted_at,
            last_milestone_thickness=referral.last_milestone_thickness,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise ReferralAlreadyExistsError(referred_id=referral.referred_id) from exc
        return _row_to_entity(row)

    async def get_by_referred_id(self, referred_id: int) -> Referral | None:
        result = await self._uow.session.execute(
            select(ReferralORM).where(ReferralORM.referred_id == referred_id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row)

    async def mark_signup_granted(
        self,
        *,
        referred_id: int,
        granted_at: datetime,
    ) -> Referral:
        result = await self._uow.session.execute(
            select(ReferralORM).where(ReferralORM.referred_id == referred_id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise _ReferralNotFoundError(f"Referral for referred_id={referred_id} not found")
        row.signup_granted_at = granted_at
        await self._uow.session.flush()
        return _row_to_entity(row)

    async def mark_milestone_granted(
        self,
        *,
        referred_id: int,
        thickness: int,
    ) -> Referral:
        result = await self._uow.session.execute(
            select(ReferralORM).where(ReferralORM.referred_id == referred_id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise _ReferralNotFoundError(f"Referral for referred_id={referred_id} not found")
        # Никогда не понижаем — только поднимаем (use-case проверяет
        # `last_milestone_thickness < thickness` перед вызовом).
        if thickness > row.last_milestone_thickness:
            row.last_milestone_thickness = thickness
            await self._uow.session.flush()
        return _row_to_entity(row)
