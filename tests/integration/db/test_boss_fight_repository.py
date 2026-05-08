"""Integration-тесты `SqlAlchemyBossFightRepository` и
`SqlAlchemyBossParticipantRepository` (Спринт 3.3-B, ГДД §10).

Покрытие:
- CRUD `boss_fights`: `add` → `get_by_id`, `save` (mutate),
  `get_active_for_player`, `get_last_global_started_at`;
- БД-инварианты `boss_fights`: CHECK-ограничения (`kind`, `status`,
  `summoner_player_id <> boss_player_id`, `lobby_ends_at > started_at`,
  `initial_boss_length_cm > 0`, `current_boss_length_cm >= 0` &
  `current_boss_length_cm <= initial_boss_length_cm`,
  `current_round >= 0`, `finished_at` ↔ `status`);
- CRUD `boss_participants`: `add` → `list_by_boss_fight`,
  `get_by_boss_fight_and_player`, `remove` (с no-op-ом);
- БД-инварианты `boss_participants`: composite-PK `(boss_fight_id, player_id)`,
  CHECK `length_at_join_cm > 0`,
  partial-unique `uq_boss_participants_one_summoner_per_boss_fight`;
- ON DELETE CASCADE: при удалении `boss_fights` row-а участники
  тоже удаляются.

Используется in-memory SQLite (`engine`/`uow` фикстуры из
`conftest.py`) — портабельное подмножество DDL покрывает оба бэкенда
(SQLite + Postgres) одинаково (см. `infrastructure/db/models/boss.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossKind,
    BossParticipant,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyBossFightRepository,
    SqlAlchemyBossParticipantRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
LOBBY_ENDS_AT = NOW + timedelta(minutes=20)


# ---------- Seed helpers ----------


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


async def _seed_summoner_and_boss(
    uow: SqlAlchemyUnitOfWork,
    *,
    summoner_tg_id: int = 100,
    boss_tg_id: int = 200,
) -> tuple[Player, Player]:
    summoner = await _seed_player(uow, tg_id=summoner_tg_id)
    boss = await _seed_player(uow, tg_id=boss_tg_id)
    return summoner, boss


def _new_boss_fight(
    *,
    summoner_player_id: int,
    boss_player_id: int,
    started_at: datetime = NOW,
    random_seed: int = 12345,
    initial_boss_length_cm: int = 400,
) -> BossFight:
    return BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        started_at=started_at,
        lobby_ends_at=started_at + timedelta(minutes=20),
        random_seed=random_seed,
        initial_boss_length_cm=initial_boss_length_cm,
    )


# ============================================================
# BOSS FIGHT REPOSITORY
# ============================================================


class TestBossFightRepositoryCrud:
    @pytest.mark.asyncio
    async def test_get_by_id_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            assert await repo.get_by_id(boss_fight_id=404) is None

    @pytest.mark.asyncio
    async def test_add_and_get_by_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )
            assert stored.id is not None
            assert stored.kind is BossKind.RAID
            assert stored.summoner_player_id == summoner.id
            assert stored.boss_player_id == boss.id
            assert stored.status is BossFightStatus.LOBBY
            assert stored.finished_at is None
            assert stored.random_seed == 12345
            assert stored.initial_boss_length_cm == 400
            assert stored.current_boss_length_cm == 400
            assert stored.current_round == 0

        async with uow:
            assert stored.id is not None
            found = await repo.get_by_id(boss_fight_id=stored.id)
            assert found is not None
            assert found.id == stored.id
            assert found.status is BossFightStatus.LOBBY
            assert found.kind is BossKind.RAID

    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_save_persists_status_transition(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        async with uow:
            saved = await repo.save(stored.mark_in_battle())
            assert saved.status is BossFightStatus.IN_BATTLE
            assert saved.id == stored.id

        async with uow:
            assert stored.id is not None
            reloaded = await repo.get_by_id(boss_fight_id=stored.id)
            assert reloaded is not None
            assert reloaded.status is BossFightStatus.IN_BATTLE
            assert reloaded.finished_at is None

    @pytest.mark.asyncio
    async def test_save_finished_sets_finished_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        finished_at = LOBBY_ENDS_AT + timedelta(minutes=60)
        async with uow:
            saved = await repo.save(stored.mark_in_battle().mark_finished(finished_at=finished_at))
            assert saved.status is BossFightStatus.FINISHED
            assert saved.finished_at == finished_at

        async with uow:
            assert stored.id is not None
            reloaded = await repo.get_by_id(boss_fight_id=stored.id)
            assert reloaded is not None
            assert reloaded.status is BossFightStatus.FINISHED
            assert reloaded.finished_at == finished_at

    @pytest.mark.asyncio
    async def test_save_cancelled_sets_finished_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        async with uow:
            saved = await repo.save(stored.mark_cancelled(cancelled_at=LOBBY_ENDS_AT))
            assert saved.status is BossFightStatus.CANCELLED
            assert saved.finished_at == LOBBY_ENDS_AT

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossFightRepository(uow=uow)
        ghost = BossFight(
            id=99999,
            kind=BossKind.RAID,
            summoner_player_id=1,
            boss_player_id=2,
            status=BossFightStatus.LOBBY,
            started_at=NOW,
            lobby_ends_at=LOBBY_ENDS_AT,
            random_seed=1,
            initial_boss_length_cm=100,
            current_boss_length_cm=100,
            current_round=0,
            finished_at=None,
        )
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost)

    @pytest.mark.asyncio
    async def test_save_without_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossFightRepository(uow=uow)
        ghost = BossFight.starting(
            kind=BossKind.RAID,
            summoner_player_id=1,
            boss_player_id=2,
            started_at=NOW,
            lobby_ends_at=LOBBY_ENDS_AT,
            random_seed=1,
            initial_boss_length_cm=100,
        )
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(ghost)


class TestBossFightRepositoryActiveForPlayer:
    @pytest.mark.asyncio
    async def test_get_active_when_none(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            assert await repo.get_active_for_player(player_id=999) is None

    @pytest.mark.asyncio
    async def test_get_active_finds_boss(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Босс активен через `boss_fights.boss_player_id`."""
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        async with uow:
            active = await repo.get_active_for_player(player_id=boss.id)
            assert active is not None
            assert active.id == stored.id

    @pytest.mark.asyncio
    async def test_get_active_finds_summoner_via_participants(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        """Саммонер активен через JOIN с `boss_participants`."""
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        fight_repo = SqlAlchemyBossFightRepository(uow=uow)
        part_repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            stored = await fight_repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )
            assert stored.id is not None
            await part_repo.add(
                BossParticipant.raider(
                    boss_fight_id=stored.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        async with uow:
            active = await fight_repo.get_active_for_player(player_id=summoner.id)
            assert active is not None
            assert active.id == stored.id

    @pytest.mark.asyncio
    async def test_get_active_finds_raider_via_participants(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        raider = await _seed_player(uow, tg_id=300)
        assert summoner.id is not None and boss.id is not None and raider.id is not None

        fight_repo = SqlAlchemyBossFightRepository(uow=uow)
        part_repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            stored = await fight_repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )
            assert stored.id is not None
            await part_repo.add(
                BossParticipant.raider(
                    boss_fight_id=stored.id,
                    player_id=raider.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        async with uow:
            active = await fight_repo.get_active_for_player(player_id=raider.id)
            assert active is not None
            assert active.id == stored.id

    @pytest.mark.asyncio
    async def test_get_active_skips_finished(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        async with uow:
            await repo.save(stored.mark_in_battle().mark_finished(finished_at=LOBBY_ENDS_AT))

        async with uow:
            assert await repo.get_active_for_player(player_id=boss.id) is None

    @pytest.mark.asyncio
    async def test_get_active_skips_cancelled(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )

        async with uow:
            await repo.save(stored.mark_cancelled(cancelled_at=LOBBY_ENDS_AT))

        async with uow:
            assert await repo.get_active_for_player(player_id=boss.id) is None


class TestBossFightRepositoryGlobalCooldown:
    @pytest.mark.asyncio
    async def test_last_global_when_none(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            assert await repo.get_last_global_started_at() is None

    @pytest.mark.asyncio
    async def test_last_global_returns_max_started_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        summoner_a = await _seed_player(uow, tg_id=10)
        boss_a = await _seed_player(uow, tg_id=20)
        summoner_b = await _seed_player(uow, tg_id=30)
        boss_b = await _seed_player(uow, tg_id=40)
        assert summoner_a.id is not None and boss_a.id is not None
        assert summoner_b.id is not None and boss_b.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        old_started = NOW - timedelta(hours=24)
        new_started = NOW
        async with uow:
            await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner_a.id,
                    boss_player_id=boss_a.id,
                    started_at=old_started,
                    random_seed=1,
                )
            )
            await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner_b.id,
                    boss_player_id=boss_b.id,
                    started_at=new_started,
                    random_seed=2,
                )
            )

        async with uow:
            last = await repo.get_last_global_started_at()
            assert last == new_started

    @pytest.mark.asyncio
    async def test_last_global_includes_cancelled(self, uow: SqlAlchemyUnitOfWork) -> None:
        # ГДД §10.1: глобальный 4-часовой кулдаун стартует с started_at,
        # отменённый бой тоже «съедает» окно.
        summoner, boss = await _seed_summoner_and_boss(uow)
        assert summoner.id is not None and boss.id is not None

        repo = SqlAlchemyBossFightRepository(uow=uow)
        async with uow:
            cancelled = await repo.add(
                _new_boss_fight(
                    summoner_player_id=summoner.id,
                    boss_player_id=boss.id,
                )
            )
            await repo.save(cancelled.mark_cancelled(cancelled_at=NOW))

        async with uow:
            last = await repo.get_last_global_started_at()
            assert last == NOW


class TestBossFightCheckConstraints:
    @pytest.mark.asyncio
    async def test_summoner_equals_boss_rejected_by_db(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`ck_boss_fights_summoner_not_boss` блокирует на уровне БД."""
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    text(
                        "INSERT INTO boss_fights "
                        "(kind, summoner_player_id, boss_player_id, status, "
                        " started_at, lobby_ends_at, random_seed, "
                        " initial_boss_length_cm, current_boss_length_cm, "
                        " current_round) "
                        "VALUES (:kind, :s, :s, 'lobby', :st, :le, :rs, "
                        " :ibl, :cbl, 0)"
                    ),
                    {
                        "kind": "raid",
                        "s": player.id,
                        "st": NOW.isoformat(),
                        "le": LOBBY_ENDS_AT.isoformat(),
                        "rs": 1,
                        "ibl": 100,
                        "cbl": 100,
                    },
                )


# ============================================================
# BOSS PARTICIPANT REPOSITORY
# ============================================================


async def _seed_boss_fight_for_participants(
    uow: SqlAlchemyUnitOfWork,
) -> tuple[BossFight, Player, Player]:
    summoner, boss = await _seed_summoner_and_boss(uow)
    assert summoner.id is not None and boss.id is not None
    repo = SqlAlchemyBossFightRepository(uow=uow)
    async with uow:
        stored = await repo.add(
            _new_boss_fight(
                summoner_player_id=summoner.id,
                boss_player_id=boss.id,
            )
        )
    return stored, summoner, boss


class TestBossParticipantRepositoryCrud:
    @pytest.mark.asyncio
    async def test_list_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            assert await repo.list_by_boss_fight(boss_fight_id=404) == ()

    @pytest.mark.asyncio
    async def test_add_summoner_and_get(self, uow: SqlAlchemyUnitOfWork) -> None:
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=120,
                    joined_at=NOW,
                )
            )
            assert stored.boss_fight_id == fight.id
            assert stored.player_id == summoner.id
            assert stored.is_summoner is True
            assert stored.length_at_join_cm == 120

        async with uow:
            found = await repo.get_by_boss_fight_and_player(
                boss_fight_id=fight.id,
                player_id=summoner.id,
            )
            assert found is not None
            assert found.is_summoner is True

    @pytest.mark.asyncio
    async def test_add_raider_and_list(self, uow: SqlAlchemyUnitOfWork) -> None:
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None
        raider = await _seed_player(uow, tg_id=300)
        assert raider.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=120,
                    joined_at=NOW,
                )
            )
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=raider.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW + timedelta(minutes=1),
                )
            )

        async with uow:
            participants = await repo.list_by_boss_fight(boss_fight_id=fight.id)
            assert len(participants) == 2
            # Ordered by joined_at, then player_id.
            assert participants[0].player_id == summoner.id
            assert participants[0].is_summoner is True
            assert participants[1].player_id == raider.id
            assert participants[1].is_summoner is False

    @pytest.mark.asyncio
    async def test_remove_existing(self, uow: SqlAlchemyUnitOfWork) -> None:
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None
        raider = await _seed_player(uow, tg_id=300)
        assert raider.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=raider.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        async with uow:
            await repo.remove(boss_fight_id=fight.id, player_id=raider.id)

        async with uow:
            assert (
                await repo.get_by_boss_fight_and_player(boss_fight_id=fight.id, player_id=raider.id)
                is None
            )

    @pytest.mark.asyncio
    async def test_remove_missing_is_noop(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            # Не должно бросать.
            await repo.remove(boss_fight_id=9999, player_id=42)


class TestBossParticipantUniqueAndCheckConstraints:
    @pytest.mark.asyncio
    async def test_player_can_join_boss_fight_only_once(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Composite-PK `(boss_fight_id, player_id)` гарантирует уникальность."""
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        with pytest.raises(DomainIntegrityError, match="failed to add boss_participant"):
            async with uow:
                await repo.add(
                    BossParticipant.raider(
                        boss_fight_id=fight.id,
                        player_id=summoner.id,
                        is_summoner=False,
                        length_at_join_cm=110,
                        joined_at=NOW + timedelta(minutes=1),
                    )
                )

    @pytest.mark.asyncio
    async def test_only_one_summoner_per_boss_fight(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Partial-unique индекс «один саммонер на рейд-бой»."""
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None
        another = await _seed_player(uow, tg_id=300)
        assert another.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        with pytest.raises(DomainIntegrityError, match="failed to add boss_participant"):
            async with uow:
                await repo.add(
                    BossParticipant.raider(
                        boss_fight_id=fight.id,
                        player_id=another.id,
                        is_summoner=True,
                        length_at_join_cm=100,
                        joined_at=NOW + timedelta(minutes=1),
                    )
                )

    @pytest.mark.asyncio
    async def test_two_raiders_one_summoner(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Несколько рейдеров с `is_summoner=false` — норм."""
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None
        raider_a = await _seed_player(uow, tg_id=300)
        raider_b = await _seed_player(uow, tg_id=400)
        assert raider_a.id is not None and raider_b.id is not None

        repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=raider_a.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW + timedelta(minutes=1),
                )
            )
            await repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=raider_b.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW + timedelta(minutes=2),
                )
            )

        async with uow:
            participants = await repo.list_by_boss_fight(boss_fight_id=fight.id)
            assert len(participants) == 3
            summoners = [p for p in participants if p.is_summoner]
            assert len(summoners) == 1
            assert summoners[0].player_id == summoner.id


class TestBossFightCascadeDelete:
    @pytest.mark.asyncio
    async def test_deleting_boss_fight_cascades_to_participants(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        """ON DELETE CASCADE: удаление `boss_fights` снимает participants."""
        fight, summoner, _boss = await _seed_boss_fight_for_participants(uow)
        assert fight.id is not None and summoner.id is not None
        raider = await _seed_player(uow, tg_id=300)
        assert raider.id is not None

        part_repo = SqlAlchemyBossParticipantRepository(uow=uow)
        async with uow:
            await part_repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=summoner.id,
                    is_summoner=True,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )
            await part_repo.add(
                BossParticipant.raider(
                    boss_fight_id=fight.id,
                    player_id=raider.id,
                    is_summoner=False,
                    length_at_join_cm=100,
                    joined_at=NOW,
                )
            )

        # SQLite по умолчанию НЕ применяет foreign keys без `PRAGMA foreign_keys=ON`.
        # Включаем pragma и удаляем boss_fight, ожидая каскад.
        async with uow:
            await uow.session.execute(text("PRAGMA foreign_keys=ON"))
            await uow.session.execute(
                text("DELETE FROM boss_fights WHERE id = :id"),
                {"id": fight.id},
            )

        async with uow:
            assert await part_repo.list_by_boss_fight(boss_fight_id=fight.id) == ()
