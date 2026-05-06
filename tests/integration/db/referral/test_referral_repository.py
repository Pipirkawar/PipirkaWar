"""Integration-тесты `SqlAlchemyReferralRepository` (Спринт 2.4.B + 2.4.E)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanMember,
    ClanMemberRole,
    ClanTitle,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.referral import Referral, ReferralAlreadyExistsError
from pipirik_wars.infrastructure.db.models import ReferralORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemyReferralRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=30)
WEEK_START = datetime(2026, 4, 26, 18, 0, tzinfo=UTC)
WEEK_END = WEEK_START + timedelta(days=7)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


async def _seed_clan(uow: SqlAlchemyUnitOfWork, *, chat_id: int) -> Clan:
    repo = SqlAlchemyClanRepository(uow=uow)
    async with uow:
        return await repo.add(
            Clan.new(
                chat_id=chat_id,
                chat_kind=ChatKind.SUPERGROUP,
                title=ClanTitle(value=f"Клан #{chat_id}"),
                now=NOW,
            ),
        )


async def _seed_membership(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan_id: int,
    player_id: int,
) -> ClanMember:
    repo = SqlAlchemyClanMembershipRepository(uow=uow)
    async with uow:
        return await repo.add(
            ClanMember(
                clan_id=clan_id,
                player_id=player_id,
                role=ClanMemberRole.MEMBER,
                joined_at=NOW,
            ),
        )


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


class TestWeeklySummaryByClan:
    """`weekly_summary_by_clan(...)` (Спринт 2.4.E.1).

    Покрывают:
    - happy-path: один клан, два member-реферера, у одного из них больше
      рефералов — top-1, top-2;
    - реферер вне клана не попадает в выборку;
    - реферал вне окна `[since, until)` не считается;
    - чужой клан не возвращает чужих рефералов;
    - сорт по `count DESC, referrer_id ASC`;
    - валидация `since >= until`.
    """

    @pytest.mark.asyncio
    async def test_returns_only_clan_members(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Member-реферер: попадает в выборку.
        member = await _seed_player(uow, tg_id=10001)
        # Не-member: НЕ должен попасть.
        outsider = await _seed_player(uow, tg_id=10002)
        # Рефералы (новые игроки) — без клана.
        ref_a = await _seed_player(uow, tg_id=20001)
        ref_b = await _seed_player(uow, tg_id=20002)
        clan = await _seed_clan(uow, chat_id=-100123)
        assert clan.id is not None
        assert member.id is not None and outsider.id is not None
        assert ref_a.id is not None and ref_b.id is not None
        await _seed_membership(uow, clan_id=clan.id, player_id=member.id)

        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            await repo.add(
                _referral(
                    referrer_id=member.id,
                    referred_id=ref_a.id,
                    created_at=WEEK_START + timedelta(hours=1),
                ),
            )
            await repo.add(
                _referral(
                    referrer_id=outsider.id,
                    referred_id=ref_b.id,
                    created_at=WEEK_START + timedelta(hours=2),
                ),
            )

        async with uow:
            summary = await repo.weekly_summary_by_clan(
                clan_id=clan.id,
                since=WEEK_START,
                until=WEEK_END,
            )
        assert len(summary) == 1
        assert summary[0].referrer_id == member.id
        assert summary[0].count == 1

    @pytest.mark.asyncio
    async def test_groups_and_orders_by_count_desc(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        # Два реферера в клане: один привёл 3 чел., второй — 1.
        ref_a_inviter = await _seed_player(uow, tg_id=11111)
        ref_b_inviter = await _seed_player(uow, tg_id=11112)
        # Рефералы:
        new_1 = await _seed_player(uow, tg_id=20001)
        new_2 = await _seed_player(uow, tg_id=20002)
        new_3 = await _seed_player(uow, tg_id=20003)
        new_4 = await _seed_player(uow, tg_id=20004)
        clan = await _seed_clan(uow, chat_id=-100200)
        assert clan.id is not None
        assert ref_a_inviter.id is not None and ref_b_inviter.id is not None
        await _seed_membership(uow, clan_id=clan.id, player_id=ref_a_inviter.id)
        await _seed_membership(uow, clan_id=clan.id, player_id=ref_b_inviter.id)

        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            for invited in (new_1, new_2, new_3):
                assert invited.id is not None
                await repo.add(
                    _referral(
                        referrer_id=ref_a_inviter.id,
                        referred_id=invited.id,
                        created_at=WEEK_START + timedelta(hours=1),
                    ),
                )
            assert new_4.id is not None
            await repo.add(
                _referral(
                    referrer_id=ref_b_inviter.id,
                    referred_id=new_4.id,
                    created_at=WEEK_START + timedelta(hours=2),
                ),
            )

        async with uow:
            summary = await repo.weekly_summary_by_clan(
                clan_id=clan.id,
                since=WEEK_START,
                until=WEEK_END,
            )
        assert len(summary) == 2
        assert summary[0].referrer_id == ref_a_inviter.id
        assert summary[0].count == 3
        assert summary[1].referrer_id == ref_b_inviter.id
        assert summary[1].count == 1

    @pytest.mark.asyncio
    async def test_filters_by_window(self, uow: SqlAlchemyUnitOfWork) -> None:
        member = await _seed_player(uow, tg_id=12001)
        ref_in = await _seed_player(uow, tg_id=22001)
        ref_before = await _seed_player(uow, tg_id=22002)
        ref_at_until = await _seed_player(uow, tg_id=22003)
        clan = await _seed_clan(uow, chat_id=-100300)
        assert clan.id is not None and member.id is not None
        await _seed_membership(uow, clan_id=clan.id, player_id=member.id)

        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            assert ref_in.id is not None
            await repo.add(
                _referral(
                    referrer_id=member.id,
                    referred_id=ref_in.id,
                    created_at=WEEK_START + timedelta(hours=1),
                ),
            )
            # До окна — не считается.
            assert ref_before.id is not None
            await repo.add(
                _referral(
                    referrer_id=member.id,
                    referred_id=ref_before.id,
                    created_at=WEEK_START - timedelta(seconds=1),
                ),
            )
            # На границе `until` — не считается (полузакрытое окно).
            assert ref_at_until.id is not None
            await repo.add(
                _referral(
                    referrer_id=member.id,
                    referred_id=ref_at_until.id,
                    created_at=WEEK_END,
                ),
            )

        async with uow:
            summary = await repo.weekly_summary_by_clan(
                clan_id=clan.id,
                since=WEEK_START,
                until=WEEK_END,
            )
        assert len(summary) == 1
        assert summary[0].count == 1

    @pytest.mark.asyncio
    async def test_other_clan_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        my_member = await _seed_player(uow, tg_id=13001)
        other_member = await _seed_player(uow, tg_id=13002)
        invited = await _seed_player(uow, tg_id=23001)
        my_clan = await _seed_clan(uow, chat_id=-100401)
        other_clan = await _seed_clan(uow, chat_id=-100402)
        assert my_clan.id is not None and other_clan.id is not None
        assert my_member.id is not None and other_member.id is not None
        await _seed_membership(uow, clan_id=my_clan.id, player_id=my_member.id)
        await _seed_membership(uow, clan_id=other_clan.id, player_id=other_member.id)

        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            assert invited.id is not None
            # Реферал от чужого клана.
            await repo.add(
                _referral(
                    referrer_id=other_member.id,
                    referred_id=invited.id,
                    created_at=WEEK_START + timedelta(hours=1),
                ),
            )

        async with uow:
            summary = await repo.weekly_summary_by_clan(
                clan_id=my_clan.id,
                since=WEEK_START,
                until=WEEK_END,
            )
        assert summary == ()

    @pytest.mark.asyncio
    async def test_empty_when_no_referrals(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100500)
        assert clan.id is not None
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            summary = await repo.weekly_summary_by_clan(
                clan_id=clan.id,
                since=WEEK_START,
                until=WEEK_END,
            )
        assert summary == ()

    @pytest.mark.asyncio
    async def test_inverse_window_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyReferralRepository(uow=uow)
        async with uow:
            with pytest.raises(ValueError, match="must be <"):
                await repo.weekly_summary_by_clan(
                    clan_id=1,
                    since=WEEK_END,
                    until=WEEK_START,
                )
