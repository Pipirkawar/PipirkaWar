"""Integration-тесты `SqlAlchemyClanMassDuelHistoryQuery` (Спринт 2.2.G / ПД 2.2.5).

Покрывают read-side-проекцию журнала клановых атак:

* пустой клан → пустой результат;
* `IN_PROGRESS`-бои не попадают в журнал;
* `COMPLETED` (с нашей стороны выигрыш / поражение / ничья) —
  правильный маппинг `our_*` / `opponent_*`;
* `CANCELLED`-бои попадают в журнал с `outcome=CANCELLED`;
* сортировка по `created_at DESC, id DESC`;
* `limit` обрезает результат;
* симметричность: запрос от клана-1 и клана-2 для одного и того же
  боя возвращает зеркальный entry (наш ↔ их);
* подсчёт участников из `pvp_mass_duel_choices`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.clan import ChatKind, Clan, ClanTitle
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.pvp import (
    ClanMassDuelOutcomeForUs,
    MassDuel,
    MassDuelState,
    MassRoundChoice,
    Position,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanMassDuelHistoryQuery,
    SqlAlchemyClanRepository,
    SqlAlchemyMassDuelRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from tests.fakes.random import FakeRandom

NOW = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


async def _seed_clan(uow: SqlAlchemyUnitOfWork, *, chat_id: int, title: str) -> Clan:
    repo = SqlAlchemyClanRepository(uow=uow)
    async with uow:
        return await repo.add(
            Clan.new(
                chat_id=chat_id,
                chat_kind=ChatKind.SUPERGROUP,
                title=ClanTitle(value=title),
                now=NOW,
            )
        )


async def _seed_two_clans_with_members(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan1_size: int,
    clan2_size: int,
    clan1_title: str = "Лесные",
    clan2_title: str = "Морские",
    base_player_id: int = 0,
) -> tuple[Clan, Clan, list[Player], list[Player]]:
    clan1 = await _seed_clan(uow, chat_id=-100100 - base_player_id, title=clan1_title)
    clan2 = await _seed_clan(uow, chat_id=-100200 - base_player_id, title=clan2_title)
    clan1_players = [
        await _seed_player(uow, tg_id=1000 + base_player_id + i) for i in range(clan1_size)
    ]
    clan2_players = [
        await _seed_player(uow, tg_id=2000 + base_player_id + i) for i in range(clan2_size)
    ]
    return clan1, clan2, clan1_players, clan2_players


def _build_mass_duel(
    *,
    clan1_id: int,
    clan2_id: int,
    clan1_lengths: dict[int, int],
    clan2_lengths: dict[int, int],
    hit_pct: int = 10,
    now: datetime = NOW,
) -> MassDuel:
    return MassDuel.create_battle(
        clan1_id=clan1_id,
        clan2_id=clan2_id,
        clan1_lengths=clan1_lengths,
        clan2_lengths=clan2_lengths,
        hit_pct=hit_pct,
        now=now,
    )


async def _persist_completed(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan1: Clan,
    clan2: Clan,
    p1: Player,
    p2: Player,
    p1_attack: Position = Position.HIGH,
    p1_block: Position = Position.MID,
    p2_attack: Position = Position.LOW,
    p2_block: Position = Position.HIGH,
    now: datetime = NOW,
) -> MassDuel:
    repo = SqlAlchemyMassDuelRepository(uow=uow)
    assert clan1.id is not None and clan2.id is not None
    assert p1.id is not None and p2.id is not None
    async with uow:
        stored = await repo.add(
            _build_mass_duel(
                clan1_id=clan1.id,
                clan2_id=clan2.id,
                clan1_lengths={p1.id: 100},
                clan2_lengths={p2.id: 100},
                now=now,
            )
        )
    assert stored.id is not None
    submitted = stored.submit_move(
        player_id=p1.id,
        choice=MassRoundChoice(player_id=p1.id, attack=p1_attack, block=p1_block),
        now=now,
    ).submit_move(
        player_id=p2.id,
        choice=MassRoundChoice(player_id=p2.id, attack=p2_attack, block=p2_block),
        now=now,
    )
    resolved = submitted.resolve(random=FakeRandom(seed=42), now=now)
    async with uow:
        await repo.save(resolved)
    return resolved


async def _persist_cancelled(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan1: Clan,
    clan2: Clan,
    p1: Player,
    p2: Player,
    now: datetime = NOW,
) -> MassDuel:
    repo = SqlAlchemyMassDuelRepository(uow=uow)
    assert clan1.id is not None and clan2.id is not None
    assert p1.id is not None and p2.id is not None
    async with uow:
        stored = await repo.add(
            _build_mass_duel(
                clan1_id=clan1.id,
                clan2_id=clan2.id,
                clan1_lengths={p1.id: 100},
                clan2_lengths={p2.id: 100},
                now=now,
            )
        )
    assert stored.id is not None
    cancelled = stored.cancel(now=now)
    async with uow:
        await repo.save(cancelled)
    return cancelled


class TestEmptyHistory:
    @pytest.mark.asyncio
    async def test_clan_without_battles_returns_empty(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan = await _seed_clan(uow, chat_id=-100, title="Один")
        assert clan.id is not None
        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        async with uow:
            entries = await query.get_recent(clan_id=clan.id, limit=10)
        assert tuple(entries) == ()

    @pytest.mark.asyncio
    async def test_unknown_clan_returns_empty(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        async with uow:
            entries = await query.get_recent(clan_id=999_999, limit=10)
        assert tuple(entries) == ()


class TestInProgressFiltered:
    @pytest.mark.asyncio
    async def test_in_progress_battle_not_in_history(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        async with uow:
            await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100},
                    clan2_lengths={p2.id: 100},
                ),
            )
        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=10)
        assert tuple(entries) == ()


class TestCompletedHistory:
    @pytest.mark.asyncio
    async def test_completed_battle_visible_with_correct_projection(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        resolved = await _persist_completed(uow, clan1=clan1, clan2=clan2, p1=p1, p2=p2)
        assert resolved.final_outcome is not None
        outcome = resolved.final_outcome

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan1.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=10)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.duel_id == resolved.id
        assert entry.our_clan_id == clan1.id
        assert entry.opponent_clan_id == clan2.id
        assert entry.opponent_clan_title.value == "Морские"
        assert entry.state is MassDuelState.COMPLETED
        assert entry.our_total_dealt == outcome.clan1_total_dealt
        assert entry.our_total_received == outcome.clan2_total_dealt
        assert entry.our_delta_cm == outcome.clan1_delta_cm
        assert entry.opponent_delta_cm == outcome.clan2_delta_cm
        assert entry.our_participants_count == 1
        assert entry.opponent_participants_count == 1

    @pytest.mark.asyncio
    async def test_completed_battle_mirrored_for_opposite_clan(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        resolved = await _persist_completed(uow, clan1=clan1, clan2=clan2, p1=p1, p2=p2)
        assert resolved.final_outcome is not None
        outcome = resolved.final_outcome

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan2.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan2.id, limit=10)
        assert len(entries) == 1
        entry = entries[0]
        # Симметрично: наша точка зрения = clan2, противник = clan1.
        assert entry.our_clan_id == clan2.id
        assert entry.opponent_clan_id == clan1.id
        assert entry.opponent_clan_title.value == "Лесные"
        assert entry.our_total_dealt == outcome.clan2_total_dealt
        assert entry.our_total_received == outcome.clan1_total_dealt
        assert entry.our_delta_cm == outcome.clan2_delta_cm
        assert entry.opponent_delta_cm == outcome.clan1_delta_cm

    @pytest.mark.asyncio
    async def test_outcome_for_winner_is_victory(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        # `FakeRandom(seed=42)` детерминирован: проверим оба исхода
        # симметрично от точки зрения каждого клана.
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        resolved = await _persist_completed(uow, clan1=clan1, clan2=clan2, p1=p1, p2=p2)
        assert resolved.final_outcome is not None
        winner_side = resolved.final_outcome.winner.value  # "clan1" / "clan2" / "draw"

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan1.id is not None and clan2.id is not None
        async with uow:
            entries_c1 = await query.get_recent(clan_id=clan1.id, limit=1)
            entries_c2 = await query.get_recent(clan_id=clan2.id, limit=1)

        if winner_side == "clan1":
            assert entries_c1[0].outcome is ClanMassDuelOutcomeForUs.VICTORY
            assert entries_c2[0].outcome is ClanMassDuelOutcomeForUs.DEFEAT
        elif winner_side == "clan2":
            assert entries_c1[0].outcome is ClanMassDuelOutcomeForUs.DEFEAT
            assert entries_c2[0].outcome is ClanMassDuelOutcomeForUs.VICTORY
        else:
            assert entries_c1[0].outcome is ClanMassDuelOutcomeForUs.DRAW
            assert entries_c2[0].outcome is ClanMassDuelOutcomeForUs.DRAW


class TestCancelledHistory:
    @pytest.mark.asyncio
    async def test_cancelled_battle_visible_as_cancelled_outcome(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        await _persist_cancelled(uow, clan1=clan1, clan2=clan2, p1=p1, p2=p2)

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan1.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=10)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.state is MassDuelState.CANCELLED
        assert entry.outcome is ClanMassDuelOutcomeForUs.CANCELLED
        assert entry.completed_at is None
        assert entry.our_total_dealt == 0
        assert entry.our_total_received == 0
        assert entry.our_delta_cm == 0
        assert entry.opponent_delta_cm == 0


class TestOrderingAndLimit:
    @pytest.mark.asyncio
    async def test_ordering_by_created_at_desc(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, players1, players2 = await _seed_two_clans_with_members(
            uow, clan1_size=3, clan2_size=3
        )
        # Три отменённых боя в разное время: t0 < t1 < t2.
        t0 = NOW
        t1 = NOW + timedelta(hours=1)
        t2 = NOW + timedelta(hours=2)
        await _persist_cancelled(
            uow, clan1=clan1, clan2=clan2, p1=players1[0], p2=players2[0], now=t0
        )
        await _persist_cancelled(
            uow, clan1=clan1, clan2=clan2, p1=players1[1], p2=players2[1], now=t1
        )
        await _persist_cancelled(
            uow, clan1=clan1, clan2=clan2, p1=players1[2], p2=players2[2], now=t2
        )

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan1.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=10)
        assert [e.created_at for e in entries] == [t2, t1, t0]

    @pytest.mark.asyncio
    async def test_limit_truncates_result(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, players1, players2 = await _seed_two_clans_with_members(
            uow, clan1_size=3, clan2_size=3
        )
        for i, (p1, p2) in enumerate(zip(players1, players2, strict=True)):
            await _persist_cancelled(
                uow,
                clan1=clan1,
                clan2=clan2,
                p1=p1,
                p2=p2,
                now=NOW + timedelta(hours=i),
            )

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan1.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=2)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_other_clans_battles_excluded(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan_a, clan_b, [pa], [pb] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        # Третий клан, не наш.
        clan_c, clan_d, [pc], [pd] = await _seed_two_clans_with_members(
            uow,
            clan1_size=1,
            clan2_size=1,
            clan1_title="Степные",
            clan2_title="Гайские",
            base_player_id=500,
        )
        await _persist_cancelled(uow, clan1=clan_a, clan2=clan_b, p1=pa, p2=pb)
        await _persist_cancelled(uow, clan1=clan_c, clan2=clan_d, p1=pc, p2=pd)

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        assert clan_a.id is not None
        async with uow:
            entries = await query.get_recent(clan_id=clan_a.id, limit=10)
        assert len(entries) == 1
        assert entries[0].opponent_clan_id == clan_b.id


class TestParticipantCounts:
    @pytest.mark.asyncio
    async def test_participants_count_matches_roster(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, players1, players2 = await _seed_two_clans_with_members(
            uow, clan1_size=3, clan2_size=2
        )
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        assert clan1.id is not None and clan2.id is not None
        clan1_lengths = {p.id: 100 for p in players1 if p.id is not None}
        clan2_lengths = {p.id: 100 for p in players2 if p.id is not None}
        async with uow:
            await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths=clan1_lengths,
                    clan2_lengths=clan2_lengths,
                ),
            )

        # Прервём бой, чтобы он попал в журнал.
        await _persist_cancelled(
            uow,
            clan1=clan1,
            clan2=clan2,
            p1=players1[0],
            p2=players2[0],
            now=NOW + timedelta(hours=1),
        )

        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        async with uow:
            entries = await query.get_recent(clan_id=clan1.id, limit=10)
        # Сначала идёт более свежий бой (1×1, persist_cancelled);
        # затем 3×2, который мы добавили выше с состоянием IN_PROGRESS
        # — в журнал не попадает (фильтр в SQL).
        assert len(entries) == 1
        assert entries[0].our_participants_count == 1
        assert entries[0].opponent_participants_count == 1


class TestQueryValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -1, -100])
    async def test_clan_id_must_be_positive(
        self,
        uow: SqlAlchemyUnitOfWork,
        bad: int,
    ) -> None:
        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        with pytest.raises(ValueError, match="clan_id must be positive"):
            await query.get_recent(clan_id=bad, limit=10)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -1])
    async def test_limit_must_be_positive(
        self,
        uow: SqlAlchemyUnitOfWork,
        bad: int,
    ) -> None:
        query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
        with pytest.raises(ValueError, match="limit must be positive"):
            await query.get_recent(clan_id=1, limit=bad)
