"""Integration-тесты `SqlAlchemyDailyHeadRepository` (Спринт 2.3.B)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pipirik_wars.domain.clan import ChatKind, Clan, ClanTitle
from pipirik_wars.domain.daily_head import (
    DailyHeadAlreadyAssignedError,
    DailyHeadAssignment,
    DailyHeadSource,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanRepository,
    SqlAlchemyDailyHeadRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
TODAY = date(2026, 5, 6)


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
                title=ClanTitle(value="Лесные братья"),
                now=NOW,
            ),
        )


def _assignment(
    *,
    clan_id: int,
    player_id: int,
    moscow_date: date = TODAY,
    source: DailyHeadSource = DailyHeadSource.BUTTON,
    bonus_cm: int = 7,
    assigned_at: datetime = NOW,
) -> DailyHeadAssignment:
    return DailyHeadAssignment(
        id=None,
        clan_id=clan_id,
        player_id=player_id,
        moscow_date=moscow_date,
        source=source,
        bonus_cm=bonus_cm,
        assigned_at=assigned_at,
    )


class TestSqlAlchemyDailyHeadRepository:
    @pytest.mark.asyncio
    async def test_get_by_clan_and_date_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            assert await repo.get_by_clan_and_date(clan_id=999, moscow_date=TODAY) is None

    @pytest.mark.asyncio
    async def test_add_then_get(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None and player.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _assignment(clan_id=clan.id, player_id=player.id, bonus_cm=15),
            )
            assert stored.id is not None
            assert stored.id > 0
            assert stored.clan_id == clan.id
            assert stored.player_id == player.id
            assert stored.moscow_date == TODAY
            assert stored.source is DailyHeadSource.BUTTON
            assert stored.bonus_cm == 15
            # ensure_utc применяется на чтении.
            assert stored.assigned_at == NOW

        async with uow:
            fetched = await repo.get_by_clan_and_date(clan_id=clan.id, moscow_date=TODAY)
            assert fetched is not None
            assert fetched.id == stored.id
            assert fetched.player_id == player.id
            assert fetched.bonus_cm == 15

    @pytest.mark.asyncio
    async def test_unique_clan_id_moscow_date(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Race кнопка+cron: повторный INSERT на тот же ключ → DailyHeadAlreadyAssignedError."""
        clan = await _seed_clan(uow, chat_id=-100123)
        player_a = await _seed_player(uow, tg_id=42)
        player_b = await _seed_player(uow, tg_id=43)
        assert clan.id is not None and player_a.id is not None and player_b.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            await repo.add(_assignment(clan_id=clan.id, player_id=player_a.id))

        with pytest.raises(DailyHeadAlreadyAssignedError) as exc:
            async with uow:
                await repo.add(
                    _assignment(
                        clan_id=clan.id,
                        player_id=player_b.id,
                        source=DailyHeadSource.CRON,
                    ),
                )
        assert exc.value.clan_id == clan.id
        assert exc.value.moscow_date == TODAY

    @pytest.mark.asyncio
    async def test_two_clans_same_day_independent(self, uow: SqlAlchemyUnitOfWork) -> None:
        """UNIQUE по (clan_id, moscow_date) — два разных клана могут иметь главу в один день."""
        clan_a = await _seed_clan(uow, chat_id=-100111)
        clan_b = await _seed_clan(uow, chat_id=-100222)
        player = await _seed_player(uow, tg_id=42)
        assert clan_a.id is not None and clan_b.id is not None and player.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            await repo.add(_assignment(clan_id=clan_a.id, player_id=player.id))
            await repo.add(_assignment(clan_id=clan_b.id, player_id=player.id, bonus_cm=12))

        async with uow:
            ga = await repo.get_by_clan_and_date(clan_id=clan_a.id, moscow_date=TODAY)
            gb = await repo.get_by_clan_and_date(clan_id=clan_b.id, moscow_date=TODAY)

        assert ga is not None and gb is not None
        assert ga.clan_id != gb.clan_id
        assert ga.bonus_cm == 7 and gb.bonus_cm == 12

    @pytest.mark.asyncio
    async def test_same_clan_different_days_independent(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None and player.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        day_b = TODAY + timedelta(days=1)
        async with uow:
            await repo.add(
                _assignment(
                    clan_id=clan.id,
                    player_id=player.id,
                    moscow_date=TODAY,
                    bonus_cm=5,
                ),
            )
            await repo.add(
                _assignment(
                    clan_id=clan.id,
                    player_id=player.id,
                    moscow_date=day_b,
                    bonus_cm=10,
                    assigned_at=NOW + timedelta(days=1),
                ),
            )

        async with uow:
            today_rec = await repo.get_by_clan_and_date(clan_id=clan.id, moscow_date=TODAY)
            tomorrow_rec = await repo.get_by_clan_and_date(clan_id=clan.id, moscow_date=day_b)

        assert today_rec is not None and tomorrow_rec is not None
        assert today_rec.bonus_cm == 5
        assert tomorrow_rec.bonus_cm == 10

    @pytest.mark.asyncio
    async def test_list_recent_for_clan_returns_empty_when_none(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            assert await repo.list_recent_for_clan(clan_id=999, limit=10) == ()

    @pytest.mark.asyncio
    async def test_list_recent_for_clan_orders_desc_with_id_tiebreaker(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        player_a = await _seed_player(uow, tg_id=42)
        player_b = await _seed_player(uow, tg_id=43)
        player_c = await _seed_player(uow, tg_id=44)
        assert clan.id is not None
        assert player_a.id is not None and player_b.id is not None and player_c.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        # Записи 1 и 2 — одинаковый assigned_at: tie-breaker — id DESC.
        async with uow:
            await repo.add(
                _assignment(
                    clan_id=clan.id,
                    player_id=player_a.id,
                    moscow_date=TODAY,
                    assigned_at=NOW,
                ),
            )
            await repo.add(
                _assignment(
                    clan_id=clan.id,
                    player_id=player_b.id,
                    moscow_date=TODAY + timedelta(days=1),
                    assigned_at=NOW,  # тот же таймстамп
                ),
            )
            await repo.add(
                _assignment(
                    clan_id=clan.id,
                    player_id=player_c.id,
                    moscow_date=TODAY + timedelta(days=2),
                    assigned_at=NOW + timedelta(days=2),  # самый свежий
                ),
            )

        async with uow:
            recent = await repo.list_recent_for_clan(clan_id=clan.id, limit=10)

        assert len(recent) == 3
        # Самый свежий (player_c) — первым.
        assert recent[0].player_id == player_c.id
        # Tie-breaker по id DESC: player_b добавлен после player_a,
        # значит у b больший id → b идёт раньше a при равном assigned_at.
        assert recent[1].player_id == player_b.id
        assert recent[2].player_id == player_a.id

    @pytest.mark.asyncio
    async def test_list_recent_for_clan_respects_limit(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        players = []
        for tg in (42, 43, 44, 45, 46):
            p = await _seed_player(uow, tg_id=tg)
            assert p.id is not None
            players.append(p)
        assert clan.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            for i, p in enumerate(players):
                await repo.add(
                    _assignment(
                        clan_id=clan.id,
                        player_id=p.id,  # type: ignore[arg-type]
                        moscow_date=TODAY + timedelta(days=i),
                        assigned_at=NOW + timedelta(days=i),
                    ),
                )

        async with uow:
            top3 = await repo.list_recent_for_clan(clan_id=clan.id, limit=3)
            top1 = await repo.list_recent_for_clan(clan_id=clan.id, limit=1)
            top0 = await repo.list_recent_for_clan(clan_id=clan.id, limit=0)

        assert len(top3) == 3
        assert len(top1) == 1
        assert top0 == ()

    @pytest.mark.asyncio
    async def test_list_recent_for_clan_filters_by_clan(self, uow: SqlAlchemyUnitOfWork) -> None:
        """list_recent_for_clan возвращает только записи указанного клана."""
        clan_a = await _seed_clan(uow, chat_id=-100111)
        clan_b = await _seed_clan(uow, chat_id=-100222)
        player = await _seed_player(uow, tg_id=42)
        assert clan_a.id is not None and clan_b.id is not None and player.id is not None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            await repo.add(_assignment(clan_id=clan_a.id, player_id=player.id))
            await repo.add(_assignment(clan_id=clan_b.id, player_id=player.id))

        async with uow:
            recent_a = await repo.list_recent_for_clan(clan_id=clan_a.id, limit=10)

        assert len(recent_a) == 1
        assert recent_a[0].clan_id == clan_a.id

    @pytest.mark.asyncio
    async def test_returned_record_has_immutable_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Возврат `add()` — новый VO с проставленным id (без мутации входного)."""
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None and player.id is not None

        original = _assignment(clan_id=clan.id, player_id=player.id)
        assert original.id is None

        repo = SqlAlchemyDailyHeadRepository(uow=uow)
        async with uow:
            saved = await repo.add(original)

        # Входной VO остался прежним.
        assert original.id is None
        # Возврат — новый VO с id.
        assert saved.id is not None
        assert saved.id > 0
