"""Integration-тесты `SqlAlchemyReferralRepository` (Спринт 2.4.B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.player import Player
from pipirik_wars.domain.referral import Referral, ReferralAlreadyExistsError
from pipirik_wars.infrastructure.db.models import ReferralORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPlayerRepository,
    SqlAlchemyReferralRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=30)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _referral(
    *,
    referrer_id: int,
    referred_id: int,
    created_at: datetime = NOW,
    signup_granted_at: datetime | None = None,
    last_milestone_thickness: int = 0,
) -> Referral:
    return Referral(
        id=None,
        referrer_id=referrer_id,
        referred_id=referred_id,
        created_at=created_at,
        signup_granted_at=signup_granted_at,
        last_milestone_thickness=last_milestone_thickness,
    )


class TestSqlAlchemyReferralRepository:
    @pytest.mark.asyncio
    async def test_get_by_referred_id_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            assert await repo.get_by_referred_id(referred_id=999) is None

    @pytest.mark.asyncio
    async def test_add_then_get(self, uow: SqlAlchemyUnitOfWork) -> None:
        referrer = await _seed_player(uow, tg_id=1001)
        referred = await _seed_player(uow, tg_id=2002)
        assert referrer.id is not None
        assert referred.id is not None
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            saved = await repo.add(
                _referral(referrer_id=referrer.id, referred_id=referred.id),
            )
        assert saved.id is not None
        assert saved.referrer_id == referrer.id
        assert saved.referred_id == referred.id
        assert saved.signup_granted_at is None
        assert saved.last_milestone_thickness == 0

        async with uow:
            found = await repo.get_by_referred_id(referred_id=referred.id)
        assert found is not None
        assert found.id == saved.id
        assert found.referrer_id == referrer.id

    @pytest.mark.asyncio
    async def test_add_duplicate_referred_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        referrer1 = await _seed_player(uow, tg_id=1001)
        referrer2 = await _seed_player(uow, tg_id=1002)
        referred = await _seed_player(uow, tg_id=2002)
        assert referrer1.id is not None
        assert referrer2.id is not None
        assert referred.id is not None
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            await repo.add(_referral(referrer_id=referrer1.id, referred_id=referred.id))
        with pytest.raises(ReferralAlreadyExistsError) as exc_info:
            async with uow:
                await repo.add(_referral(referrer_id=referrer2.id, referred_id=referred.id))
        assert exc_info.value.referred_id == referred.id

    @pytest.mark.asyncio
    async def test_mark_signup_granted_updates_timestamp(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        referrer = await _seed_player(uow, tg_id=1001)
        referred = await _seed_player(uow, tg_id=2002)
        assert referrer.id is not None
        assert referred.id is not None
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            await repo.add(_referral(referrer_id=referrer.id, referred_id=referred.id))
        async with uow:
            updated = await repo.mark_signup_granted(
                referred_id=referred.id,
                granted_at=LATER,
            )
        assert updated.signup_granted_at == LATER

        async with uow:
            persisted = await repo.get_by_referred_id(referred_id=referred.id)
        assert persisted is not None
        assert persisted.signup_granted_at == LATER

    @pytest.mark.asyncio
    async def test_mark_milestone_granted_raises_thickness(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        referrer = await _seed_player(uow, tg_id=1001)
        referred = await _seed_player(uow, tg_id=2002)
        assert referrer.id is not None
        assert referred.id is not None
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            await repo.add(_referral(referrer_id=referrer.id, referred_id=referred.id))
        # 0 -> 3
        async with uow:
            updated = await repo.mark_milestone_granted(
                referred_id=referred.id,
                thickness=3,
            )
        assert updated.last_milestone_thickness == 3
        # 3 -> 5 (поднимаем)
        async with uow:
            updated = await repo.mark_milestone_granted(
                referred_id=referred.id,
                thickness=5,
            )
        assert updated.last_milestone_thickness == 5
        # 5 -> 3 (не понижаем; поведение «никогда не понижаем»)
        async with uow:
            updated = await repo.mark_milestone_granted(
                referred_id=referred.id,
                thickness=3,
            )
        assert updated.last_milestone_thickness == 5

    @pytest.mark.asyncio
    async def test_self_referral_check_constraint(self, uow: SqlAlchemyUnitOfWork) -> None:
        """ck_referrals_no_self_referral на уровне БД (доменный VO тоже бьёт это,
        но тест на CHECK-constraint важен как last-line-of-defense)."""
        # Доменный конструктор не позволит создать само-реферал, поэтому
        # проверяем, что БД-CHECK сработает через прямой ORM-INSERT
        # (минуя `Referral.__post_init__`).
        player = await _seed_player(uow, tg_id=1001)
        assert player.id is not None
        with pytest.raises(IntegrityError) as exc_info:
            async with uow:
                uow.session.add(
                    ReferralORM(
                        referrer_id=player.id,
                        referred_id=player.id,
                        created_at=NOW,
                        signup_granted_at=None,
                        last_milestone_thickness=0,
                    ),
                )
                await uow.session.flush()
        assert "check" in str(exc_info.value).lower()
