"""In-memory фейк `IReferralRepository` для unit-тестов 2.4.x."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from pipirik_wars.domain.referral import (
    IReferralRepository,
    Referral,
    ReferralAlreadyExistsError,
)


class _ReferralNotFoundError(KeyError):
    """Внутренняя ошибка фейка — соответствует поведению SQL-репо."""


@dataclass
class FakeReferralRepository(IReferralRepository):
    """In-memory таблица `referrals`.

    Список референтных записей + автоинкрементный id. UNIQUE на
    `referred_id` симулирует БД-индекс: повторный `add()` с тем же
    `referred_id` бросает `ReferralAlreadyExistsError`.
    """

    items: list[Referral] = field(default_factory=list)
    _next_id: int = 1

    async def add(self, referral: Referral) -> Referral:
        # БД-уровневая проверка UNIQUE-индекса по `referred_id`.
        existing = await self.get_by_referred_id(referral.referred_id)
        if existing is not None:
            raise ReferralAlreadyExistsError(referred_id=referral.referred_id)
        if referral.id is None:
            saved = replace(referral, id=self._next_id)
            self._next_id += 1
        else:
            saved = referral
            self._next_id = max(self._next_id, referral.id + 1)
        self.items.append(saved)
        return saved

    async def get_by_referred_id(self, referred_id: int) -> Referral | None:
        for entry in self.items:
            if entry.referred_id == referred_id:
                return entry
        return None

    async def mark_signup_granted(
        self,
        *,
        referred_id: int,
        granted_at: datetime,
    ) -> Referral:
        for idx, entry in enumerate(self.items):
            if entry.referred_id == referred_id:
                updated = replace(entry, signup_granted_at=granted_at)
                self.items[idx] = updated
                return updated
        raise _ReferralNotFoundError(f"Referral for referred_id={referred_id} not found")

    async def mark_milestone_granted(
        self,
        *,
        referred_id: int,
        thickness: int,
    ) -> Referral:
        for idx, entry in enumerate(self.items):
            if entry.referred_id == referred_id:
                if thickness > entry.last_milestone_thickness:
                    updated = replace(entry, last_milestone_thickness=thickness)
                    self.items[idx] = updated
                    return updated
                return entry
        raise _ReferralNotFoundError(f"Referral for referred_id={referred_id} not found")


__all__ = ["FakeReferralRepository"]
