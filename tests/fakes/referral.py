"""In-memory фейк `IReferralRepository` для unit-тестов 2.4.x."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from pipirik_wars.domain.referral import (
    IReferralRepository,
    Referral,
    ReferralAlreadyExistsError,
    WeeklyClanReferralEntry,
)


class _ReferralNotFoundError(KeyError):
    """Внутренняя ошибка фейка — соответствует поведению SQL-репо."""


@dataclass
class FakeReferralRepository(IReferralRepository):
    """In-memory таблица `referrals`.

    Список референтных записей + автоинкрементный id. UNIQUE на
    `referred_id` симулирует БД-индекс: повторный `add()` с тем же
    `referred_id` бросает `ReferralAlreadyExistsError`.

    Поле `clan_members` — список пар `(clan_id, player_id)`,
    моделирующее `clan_members`-таблицу для метода
    `weekly_summary_by_clan(...)`. SQL-реализация делает INNER JOIN
    `referrals.referrer_id = clan_members.player_id` — фейк делает
    то же самое прямым перебором. Тесты, которым реферальная
    weekly-агрегация не нужна, могут оставить `clan_members=[]`.
    """

    items: list[Referral] = field(default_factory=list)
    clan_members: list[tuple[int, int]] = field(default_factory=list)
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

    async def weekly_summary_by_clan(
        self,
        *,
        clan_id: int,
        since: datetime,
        until: datetime,
    ) -> Sequence[WeeklyClanReferralEntry]:
        if since >= until:
            raise ValueError(f"weekly_summary_by_clan: since ({since}) must be < until ({until})")
        # Имитация SQL-JOIN-а: берём referrer_id-ы, которые есть в
        # `clan_members(clan_id=:cid)`, и считаем по ним рефералов
        # за окно `[since, until)`.
        member_player_ids = {pid for cid, pid in self.clan_members if cid == clan_id}
        counter: Counter[int] = Counter()
        for entry in self.items:
            if entry.referrer_id not in member_player_ids:
                continue
            if not (since <= entry.created_at < until):
                continue
            counter[entry.referrer_id] += 1
        # Стабильная сортировка: count DESC, referrer_id ASC.
        ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        return tuple(
            WeeklyClanReferralEntry(referrer_id=referrer_id, count=count)
            for referrer_id, count in ordered
        )


__all__ = ["FakeReferralRepository"]
