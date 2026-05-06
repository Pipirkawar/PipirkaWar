"""Integration-тесты `SqlAlchemyMassDuelRepository` (Спринт 2.2.D).

Покрывают полный жизненный цикл агрегата `MassDuel` через persistence:

* IN_PROGRESS → save/load round-trip (без submit-ов);
* IN_PROGRESS → submit_move (один игрок) → save/load (выбор сохранён);
* IN_PROGRESS → resolve(...) → save/load (COMPLETED, damage_entries в
  отдельной таблице);
* IN_PROGRESS → cancel(...) → save/load (CANCELLED, без final-полей);
* save() новых damage_entries не дублирует существующие (иммутабельность);
* save() с изменённым ростером отклоняется (frozen-roster инвариант);
* add() с pre-set id отклоняется;
* save() без id или несуществующего id отклоняется;
* unequal-роуст 3v1 проверяет, что параллельные кортежи восстанавливаются
  в правильном порядке.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.clan import ChatKind, Clan, ClanTitle
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.pvp import (
    MassDuel,
    MassDuelState,
    MassRoundChoice,
    Position,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanRepository,
    SqlAlchemyMassDuelRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError
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
) -> tuple[Clan, Clan, list[Player], list[Player]]:
    clan1 = await _seed_clan(uow, chat_id=-100100, title="Лесные")
    clan2 = await _seed_clan(uow, chat_id=-100200, title="Морские")
    clan1_players = [await _seed_player(uow, tg_id=1000 + i) for i in range(clan1_size)]
    clan2_players = [await _seed_player(uow, tg_id=2000 + i) for i in range(clan2_size)]
    return clan1, clan2, clan1_players, clan2_players


def _build_mass_duel(
    *,
    clan1_id: int,
    clan2_id: int,
    clan1_lengths: dict[int, int],
    clan2_lengths: dict[int, int],
    hit_pct: int = 10,
) -> MassDuel:
    return MassDuel.create_battle(
        clan1_id=clan1_id,
        clan2_id=clan2_id,
        clan1_lengths=clan1_lengths,
        clan2_lengths=clan2_lengths,
        hit_pct=hit_pct,
        now=NOW,
    )


class TestInProgressPersistence:
    @pytest.mark.asyncio
    async def test_add_in_progress_battle_assigns_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1, p2], [p3, p4] = await _seed_two_clans_with_members(
            uow, clan1_size=2, clan2_size=2
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        assert p3.id is not None and p4.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={p1.id: 100, p2.id: 80},
            clan2_lengths={p3.id: 90, p4.id: 70},
        )
        async with uow:
            stored = await repo.add(battle)

        assert stored.id is not None
        assert stored.state is MassDuelState.IN_PROGRESS
        assert stored.clan1_id == clan1.id
        assert stored.clan2_id == clan2.id
        assert stored.hit_pct == 10
        assert stored.created_at == NOW
        assert stored.completed_at is None
        assert stored.cancelled_at is None
        assert stored.final_outcome is None
        assert stored.clan1_member_ids == (p1.id, p2.id)
        assert stored.clan2_member_ids == (p3.id, p4.id)
        assert stored.clan1_initial_lengths == (100, 80)
        assert stored.clan2_initial_lengths == (90, 70)
        assert stored.clan1_choices == (None, None)
        assert stored.clan2_choices == (None, None)

    @pytest.mark.asyncio
    async def test_get_by_id_round_trip_no_submissions(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1, p2], [p3, p4] = await _seed_two_clans_with_members(
            uow, clan1_size=2, clan2_size=2
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        assert p3.id is not None and p4.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100, p2.id: 80},
                    clan2_lengths={p3.id: 90, p4.id: 70},
                ),
            )
        assert stored.id is not None

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded == stored

    @pytest.mark.asyncio
    async def test_get_by_id_missing_returns_none(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        async with uow:
            assert await repo.get_by_id(duel_id=99999) is None


class TestSubmitMovePersistence:
    @pytest.mark.asyncio
    async def test_save_after_submit_move_persists_choice(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1, p2], [p3, p4] = await _seed_two_clans_with_members(
            uow, clan1_size=2, clan2_size=2
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        assert p3.id is not None and p4.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={p1.id: 100, p2.id: 80},
            clan2_lengths={p3.id: 90, p4.id: 70},
        )
        async with uow:
            stored = await repo.add(battle)
        assert stored.id is not None

        choice = MassRoundChoice(player_id=p1.id, attack=Position.HIGH, block=Position.MID)
        with_submit = stored.submit_move(player_id=p1.id, choice=choice, now=NOW)
        async with uow:
            saved = await repo.save(with_submit)

        assert saved.clan1_choices[0] == choice
        assert saved.clan1_choices[1] is None
        assert saved.clan2_choices == (None, None)

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded is not None
        assert loaded == saved

    @pytest.mark.asyncio
    async def test_save_after_all_submitted_keeps_in_progress(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={p1.id: 100},
            clan2_lengths={p2.id: 100},
        )
        async with uow:
            stored = await repo.add(battle)
        assert stored.id is not None

        with_p1 = stored.submit_move(
            player_id=p1.id,
            choice=MassRoundChoice(player_id=p1.id, attack=Position.HIGH, block=Position.MID),
            now=NOW,
        )
        with_both = with_p1.submit_move(
            player_id=p2.id,
            choice=MassRoundChoice(player_id=p2.id, attack=Position.LOW, block=Position.HIGH),
            now=NOW,
        )
        async with uow:
            saved = await repo.save(with_both)

        # Все ещё IN_PROGRESS — resolve(...) ещё не вызывался.
        assert saved.state is MassDuelState.IN_PROGRESS
        assert saved.is_ready_to_resolve is True
        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded == saved


class TestCompletedPersistence:
    @pytest.mark.asyncio
    async def test_resolve_persists_outcome_and_damage_entries(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={p1.id: 100},
            clan2_lengths={p2.id: 100},
        )
        async with uow:
            stored = await repo.add(battle)
        assert stored.id is not None

        with_p1 = stored.submit_move(
            player_id=p1.id,
            choice=MassRoundChoice(player_id=p1.id, attack=Position.HIGH, block=Position.MID),
            now=NOW,
        )
        with_both = with_p1.submit_move(
            player_id=p2.id,
            choice=MassRoundChoice(player_id=p2.id, attack=Position.LOW, block=Position.HIGH),
            now=NOW,
        )
        resolved = with_both.resolve(random=FakeRandom(seed=42), now=NOW)
        assert resolved.state is MassDuelState.COMPLETED
        assert resolved.final_outcome is not None

        async with uow:
            saved = await repo.save(resolved)

        assert saved.state is MassDuelState.COMPLETED
        assert saved.final_outcome is not None
        assert saved.final_outcome == resolved.final_outcome
        # Zero-sum инвариант сохранился через persistence:
        assert saved.final_outcome.clan1_delta_cm + saved.final_outcome.clan2_delta_cm == 0

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded == saved

    @pytest.mark.asyncio
    async def test_save_after_resolve_does_not_duplicate_damage_entries(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Идемпотентный save после resolve не пишет damage_entries дважды."""
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100},
                    clan2_lengths={p2.id: 100},
                ),
            )
        assert stored.id is not None

        with_both = stored.submit_move(
            player_id=p1.id,
            choice=MassRoundChoice(player_id=p1.id, attack=Position.HIGH, block=Position.MID),
            now=NOW,
        ).submit_move(
            player_id=p2.id,
            choice=MassRoundChoice(player_id=p2.id, attack=Position.LOW, block=Position.HIGH),
            now=NOW,
        )
        resolved = with_both.resolve(random=FakeRandom(seed=42), now=NOW)

        async with uow:
            await repo.save(resolved)
        # Повторный save идентичного агрегата не должен раздувать
        # damage_entries.
        async with uow:
            saved_twice = await repo.save(resolved)

        assert saved_twice.final_outcome is not None
        assert resolved.final_outcome is not None
        assert len(saved_twice.final_outcome.outcome.damage_entries) == len(
            resolved.final_outcome.outcome.damage_entries
        )


class TestCancelledPersistence:
    @pytest.mark.asyncio
    async def test_save_after_cancel_persists_terminal_state(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100},
                    clan2_lengths={p2.id: 100},
                ),
            )
        assert stored.id is not None

        cancelled = stored.cancel(now=NOW)
        async with uow:
            saved = await repo.save(cancelled)
        assert saved.state is MassDuelState.CANCELLED
        assert saved.cancelled_at == NOW
        assert saved.completed_at is None
        assert saved.final_outcome is None

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded == saved


class TestErrorCases:
    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1], [p2] = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100},
                    clan2_lengths={p2.id: 100},
                ),
            )
        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_save_without_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        battle = _build_mass_duel(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 100},
        )
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(battle)

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        battle = _build_mass_duel(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 100},
        )
        ghost = replace(battle, id=99999)
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost)

    @pytest.mark.asyncio
    async def test_save_with_modified_roster_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, [p1, p2], [p3] = await _seed_two_clans_with_members(
            uow, clan1_size=2, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert p1.id is not None and p2.id is not None
        assert p3.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        async with uow:
            stored = await repo.add(
                _build_mass_duel(
                    clan1_id=clan1.id,
                    clan2_id=clan2.id,
                    clan1_lengths={p1.id: 100, p2.id: 80},
                    clan2_lengths={p3.id: 90},
                ),
            )
        assert stored.id is not None

        # Подменим ростер вручную (домен такого не позволил бы, но
        # репозиторий должен защищать как last-line-of-defense).
        tampered = replace(
            stored, clan1_member_ids=(p1.id,), clan1_initial_lengths=(100,), clan1_choices=(None,)
        )
        with pytest.raises(DomainIntegrityError, match="roster mismatch"):
            async with uow:
                await repo.save(tampered)


class TestUnequalRosters:
    @pytest.mark.asyncio
    async def test_3v1_round_trip_preserves_parallel_tuples(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, clan1_players, clan2_players = await _seed_two_clans_with_members(
            uow, clan1_size=3, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        c1_ids: list[int] = []
        for p in clan1_players:
            assert p.id is not None
            c1_ids.append(p.id)
        c2_ids: list[int] = []
        for p in clan2_players:
            assert p.id is not None
            c2_ids.append(p.id)
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={
                c1_ids[0]: 50,
                c1_ids[1]: 70,
                c1_ids[2]: 90,
            },
            clan2_lengths={c2_ids[0]: 100},
        )
        async with uow:
            stored = await repo.add(battle)
        assert stored.id is not None

        async with uow:
            loaded = await repo.get_by_id(duel_id=stored.id)
        assert loaded == stored
        # Параллельные кортежи восстановлены в правильном порядке
        # (sorted by player_id).
        assert loaded is not None
        assert loaded.clan1_member_ids == tuple(sorted(c1_ids))
        # Длины параллельны и не перепутаны.
        for member_id, length in zip(
            loaded.clan1_member_ids, loaded.clan1_initial_lengths, strict=True
        ):
            idx = c1_ids.index(member_id)
            assert length == [50, 70, 90][idx]


class TestFindMostRecentForClan:
    """Запрос `find_most_recent_for_clan(clan_id)` (Спринт 2.2.E, для cooldown-проверки)."""

    @pytest.mark.asyncio
    async def test_returns_none_when_clan_has_no_battles(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, _clan2, _, _ = await _seed_two_clans_with_members(uow, clan1_size=1, clan2_size=1)
        assert clan1.id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        async with uow:
            result = await repo.find_most_recent_for_clan(clan_id=clan1.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_battle_when_clan_is_attacker(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, clan1_players, clan2_players = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert clan1_players[0].id is not None and clan2_players[0].id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={clan1_players[0].id: 50},
            clan2_lengths={clan2_players[0].id: 60},
        )
        async with uow:
            stored = await repo.add(battle)
        async with uow:
            recent = await repo.find_most_recent_for_clan(clan_id=clan1.id)
        assert recent is not None
        assert recent.id == stored.id

    @pytest.mark.asyncio
    async def test_returns_battle_when_clan_is_defender(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, clan1_players, clan2_players = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert clan1_players[0].id is not None and clan2_players[0].id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)
        battle = _build_mass_duel(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={clan1_players[0].id: 50},
            clan2_lengths={clan2_players[0].id: 60},
        )
        async with uow:
            stored = await repo.add(battle)
        async with uow:
            recent = await repo.find_most_recent_for_clan(clan_id=clan2.id)
        assert recent is not None
        assert recent.id == stored.id

    @pytest.mark.asyncio
    async def test_returns_most_recent_among_multiple_battles(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        clan1, clan2, clan1_players, clan2_players = await _seed_two_clans_with_members(
            uow, clan1_size=1, clan2_size=1
        )
        assert clan1.id is not None and clan2.id is not None
        assert clan1_players[0].id is not None and clan2_players[0].id is not None
        repo = SqlAlchemyMassDuelRepository(uow=uow)

        early = MassDuel.create_battle(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={clan1_players[0].id: 50},
            clan2_lengths={clan2_players[0].id: 60},
            hit_pct=10,
            now=datetime(2026, 5, 5, 8, 0, tzinfo=UTC),
        )
        late = MassDuel.create_battle(
            clan1_id=clan1.id,
            clan2_id=clan2.id,
            clan1_lengths={clan1_players[0].id: 50},
            clan2_lengths={clan2_players[0].id: 60},
            hit_pct=10,
            now=datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
        )
        async with uow:
            await repo.add(early)
            stored_late = await repo.add(late)
        async with uow:
            recent = await repo.find_most_recent_for_clan(clan_id=clan1.id)
        assert recent is not None
        assert recent.id == stored_late.id
