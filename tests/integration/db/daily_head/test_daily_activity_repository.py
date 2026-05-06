"""Integration-тесты `SqlAlchemyDailyActivityRepository` (Спринт 2.3.B)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanMember,
    ClanTitle,
)
from pipirik_wars.domain.player import Player, PlayerStatus
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.infrastructure.db.models import DailyActiveORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyDailyActivityRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
TODAY = date(2026, 5, 6)


class _FakeClock(IClock):
    """Замороженные часы — `moscow_date()` всегда возвращает одну и ту же дату."""

    __slots__ = ("_moscow_date", "_now")

    def __init__(self, *, moscow_date: date, now: datetime = NOW) -> None:
        self._moscow_date = moscow_date
        self._now = now

    def now(self) -> datetime:
        return self._now

    def moscow_date(self) -> date:
        return self._moscow_date

    def moscow_datetime(self) -> datetime:
        # Не используется в тестах; для совместимости с интерфейсом.
        return self._now


async def _seed_player(
    uow: SqlAlchemyUnitOfWork,
    *,
    tg_id: int,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        player = await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))
        if status is not PlayerStatus.ACTIVE:
            assert player.id is not None
            frozen = player.freeze(now=NOW)
            return await repo.save(frozen)
        return player


async def _seed_clan(uow: SqlAlchemyUnitOfWork, *, chat_id: int) -> Clan:
    repo = SqlAlchemyClanRepository(uow=uow)
    async with uow:
        return await repo.add(
            Clan.new(
                chat_id=chat_id,
                chat_kind=ChatKind.SUPERGROUP,
                title=ClanTitle(value="Лесные братья"),
                now=NOW,
            ),
        )


async def _add_membership(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan_id: int,
    player_id: int,
) -> None:
    repo = SqlAlchemyClanMembershipRepository(uow=uow)
    async with uow:
        await repo.add(
            ClanMember.new(clan_id=clan_id, player_id=player_id, now=NOW),
        )


async def _record_activity(
    uow: SqlAlchemyUnitOfWork,
    *,
    user_id: int,
    on_date: date,
) -> None:
    """Прямой INSERT в `daily_active` — middleware появится в 2.3.E."""
    async with uow:
        uow.session.add(
            DailyActiveORM(
                date=on_date,
                user_id=user_id,
                last_at=NOW,
            ),
        )


class TestSqlAlchemyDailyActivityRepository:
    @pytest.mark.asyncio
    async def test_empty_clan_returns_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            assert await repo.list_active_member_ids(clan_id=999, within_days=7) == ()

    @pytest.mark.asyncio
    async def test_active_member_within_window(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None and player.id is not None
        await _add_membership(uow, clan_id=clan.id, player_id=player.id)
        await _record_activity(uow, user_id=player.id, on_date=TODAY)

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        assert ids == (player.id,)

    @pytest.mark.asyncio
    async def test_inactive_member_outside_window_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        active_player = await _seed_player(uow, tg_id=42)
        stale_player = await _seed_player(uow, tg_id=43)
        assert clan.id is not None
        assert active_player.id is not None and stale_player.id is not None

        await _add_membership(uow, clan_id=clan.id, player_id=active_player.id)
        await _add_membership(uow, clan_id=clan.id, player_id=stale_player.id)

        # active_player — был активен 3 дня назад (внутри окна 7 дней).
        await _record_activity(
            uow,
            user_id=active_player.id,
            on_date=TODAY - timedelta(days=3),
        )
        # stale_player — был активен 10 дней назад (за окном).
        await _record_activity(
            uow,
            user_id=stale_player.id,
            on_date=TODAY - timedelta(days=10),
        )

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        assert ids == (active_player.id,)

    @pytest.mark.asyncio
    async def test_within_days_window_inclusive(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Окно `within_days=7` включает today и предыдущие 6 дней (всего 7 точек)."""
        clan = await _seed_clan(uow, chat_id=-100123)
        # Сегодня (within_days=7): дни TODAY..TODAY-6 включительно.
        # Граничный игрок активен на TODAY-6 (попадает) и не активен на TODAY-7 (не попадает).
        player_in = await _seed_player(uow, tg_id=42)
        player_out = await _seed_player(uow, tg_id=43)
        assert clan.id is not None
        assert player_in.id is not None and player_out.id is not None

        await _add_membership(uow, clan_id=clan.id, player_id=player_in.id)
        await _add_membership(uow, clan_id=clan.id, player_id=player_out.id)
        await _record_activity(uow, user_id=player_in.id, on_date=TODAY - timedelta(days=6))
        await _record_activity(uow, user_id=player_out.id, on_date=TODAY - timedelta(days=7))

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        assert ids == (player_in.id,)

    @pytest.mark.asyncio
    async def test_frozen_player_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        """FROZEN-игрок не попадает в выборку даже если активность есть."""
        clan = await _seed_clan(uow, chat_id=-100123)
        active_player = await _seed_player(uow, tg_id=42)
        frozen_player = await _seed_player(uow, tg_id=43, status=PlayerStatus.FROZEN)
        assert clan.id is not None
        assert active_player.id is not None and frozen_player.id is not None

        await _add_membership(uow, clan_id=clan.id, player_id=active_player.id)
        await _add_membership(uow, clan_id=clan.id, player_id=frozen_player.id)
        await _record_activity(uow, user_id=active_player.id, on_date=TODAY)
        await _record_activity(uow, user_id=frozen_player.id, on_date=TODAY)

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        assert ids == (active_player.id,)

    @pytest.mark.asyncio
    async def test_other_clan_members_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Активный игрок из другого клана не попадает в выборку."""
        clan_a = await _seed_clan(uow, chat_id=-100111)
        clan_b = await _seed_clan(uow, chat_id=-100222)
        player_a = await _seed_player(uow, tg_id=42)
        player_b = await _seed_player(uow, tg_id=43)
        assert clan_a.id is not None and clan_b.id is not None
        assert player_a.id is not None and player_b.id is not None

        await _add_membership(uow, clan_id=clan_a.id, player_id=player_a.id)
        await _add_membership(uow, clan_id=clan_b.id, player_id=player_b.id)
        await _record_activity(uow, user_id=player_a.id, on_date=TODAY)
        await _record_activity(uow, user_id=player_b.id, on_date=TODAY)

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids_a = await repo.list_active_member_ids(clan_id=clan_a.id, within_days=7)

        assert ids_a == (player_a.id,)

    @pytest.mark.asyncio
    async def test_member_without_activity_excluded(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Член клана без записи активности — не активен, не попадает."""
        clan = await _seed_clan(uow, chat_id=-100123)
        player_seen = await _seed_player(uow, tg_id=42)
        player_unseen = await _seed_player(uow, tg_id=43)
        assert clan.id is not None
        assert player_seen.id is not None and player_unseen.id is not None

        await _add_membership(uow, clan_id=clan.id, player_id=player_seen.id)
        await _add_membership(uow, clan_id=clan.id, player_id=player_unseen.id)
        await _record_activity(uow, user_id=player_seen.id, on_date=TODAY)

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        assert ids == (player_seen.id,)

    @pytest.mark.asyncio
    async def test_duplicate_activity_records_deduplicated(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Несколько записей активности → один user_id (DISTINCT)."""
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None and player.id is not None

        await _add_membership(uow, clan_id=clan.id, player_id=player.id)
        # Активность в нескольких разных днях окна.
        await _record_activity(uow, user_id=player.id, on_date=TODAY)
        await _record_activity(uow, user_id=player.id, on_date=TODAY - timedelta(days=1))
        await _record_activity(uow, user_id=player.id, on_date=TODAY - timedelta(days=2))

        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        async with uow:
            ids = await repo.list_active_member_ids(clan_id=clan.id, within_days=7)

        # DISTINCT — один раз.
        assert ids == (player.id,)

    @pytest.mark.asyncio
    async def test_within_days_must_be_positive(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyDailyActivityRepository(
            uow=uow,
            clock=_FakeClock(moscow_date=TODAY),
        )
        with pytest.raises(ValueError, match="within_days must be >= 1"):
            async with uow:
                await repo.list_active_member_ids(clan_id=1, within_days=0)
