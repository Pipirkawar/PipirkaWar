"""Integration-тесты `SqlAlchemyCaravanRepository` и
`SqlAlchemyCaravanParticipantRepository` (Спринт 3.2-B, ГДД §9).

Покрытие:
- CRUD `caravans`: `add` → `get_by_id`, `save` (mutate), `get_active_by_clan`,
  `get_last_finished_at_for_clan`;
- БД-инварианты `caravans`: partial-unique «один активный караван на клан-
  отправителя» (`uq_caravans_one_active_per_sender`),
  CHECK-ограничения (`status`, `sender_clan_id <> receiver_clan_id`,
  `lobby_ends_at > started_at`, `battle_ends_at > lobby_ends_at`,
  `finished_at` ↔ `status`);
- CRUD `caravan_participants`: `add` → `list_by_caravan` /
  `list_by_caravan_and_role`, `remove` (с no-op-ом);
- БД-инварианты `caravan_participants`: composite-PK / UNIQUE
  `(caravan_id, player_id)`; CHECK на роль, лидера-караванщика,
  contribution ↔ role; partial-unique «один лидер на караван»
  (`uq_caravan_participants_one_leader_per_caravan`);
- ON DELETE CASCADE: при удалении `caravans` row-а участники
  тоже удаляются.

Используется in-memory SQLite (`engine`/`uow` фикстуры из
`conftest.py`) — портабельное подмножество DDL покрывает оба бэкенда
(SQLite + Postgres) одинаково (см. `infrastructure/db/models/caravan.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanContribution,
    CaravanParticipant,
    CaravanRole,
    CaravanStatus,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanTitle,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyCaravanParticipantRepository,
    SqlAlchemyCaravanRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
LOBBY_ENDS_AT = NOW + timedelta(minutes=20)
BATTLE_ENDS_AT = LOBBY_ENDS_AT + timedelta(minutes=60)


# ---------- Seed helpers ----------


async def _seed_clan(uow: SqlAlchemyUnitOfWork, *, chat_id: int) -> Clan:
    repo = SqlAlchemyClanRepository(uow=uow)
    async with uow:
        return await repo.add(
            Clan.new(
                chat_id=chat_id,
                chat_kind=ChatKind.SUPERGROUP,
                title=ClanTitle(value=f"Clan{chat_id}"),
                now=NOW,
            )
        )


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _new_caravan(
    *,
    sender_clan_id: int,
    receiver_clan_id: int,
    leader_player_id: int,
    started_at: datetime = NOW,
    random_seed: int = 12345,
) -> Caravan:
    return Caravan.starting(
        sender_clan_id=sender_clan_id,
        receiver_clan_id=receiver_clan_id,
        leader_player_id=leader_player_id,
        started_at=started_at,
        lobby_ends_at=started_at + timedelta(minutes=20),
        battle_ends_at=started_at + timedelta(minutes=80),
        random_seed=random_seed,
    )


async def _seed_clans_and_leader(
    uow: SqlAlchemyUnitOfWork,
    *,
    sender_chat_id: int = -100111,
    receiver_chat_id: int = -100222,
    leader_tg_id: int = 100,
) -> tuple[Clan, Clan, Player]:
    sender = await _seed_clan(uow, chat_id=sender_chat_id)
    receiver = await _seed_clan(uow, chat_id=receiver_chat_id)
    leader = await _seed_player(uow, tg_id=leader_tg_id)
    return sender, receiver, leader


# ============================================================
# CARAVAN REPOSITORY
# ============================================================


class TestCaravanRepositoryCrud:
    @pytest.mark.asyncio
    async def test_get_by_id_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            assert await repo.get_by_id(caravan_id=404) is None

    @pytest.mark.asyncio
    async def test_add_and_get_by_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )
            assert stored.id is not None
            assert stored.sender_clan_id == sender.id
            assert stored.receiver_clan_id == receiver.id
            assert stored.leader_player_id == leader.id
            assert stored.status is CaravanStatus.LOBBY
            assert stored.finished_at is None
            assert stored.random_seed == 12345

        async with uow:
            assert stored.id is not None
            found = await repo.get_by_id(caravan_id=stored.id)
            assert found is not None
            assert found.id == stored.id
            assert found.status is CaravanStatus.LOBBY

    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        # Повторный add с уже выставленным id — запрещено.
        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_save_persists_status_transition(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        async with uow:
            saved = await repo.save(stored.mark_in_battle())
            assert saved.status is CaravanStatus.IN_BATTLE
            assert saved.id == stored.id

        async with uow:
            assert stored.id is not None
            reloaded = await repo.get_by_id(caravan_id=stored.id)
            assert reloaded is not None
            assert reloaded.status is CaravanStatus.IN_BATTLE
            assert reloaded.finished_at is None

    @pytest.mark.asyncio
    async def test_save_finished_sets_finished_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        finished_at = BATTLE_ENDS_AT
        async with uow:
            saved = await repo.save(stored.mark_in_battle().mark_finished(finished_at=finished_at))
            assert saved.status is CaravanStatus.FINISHED
            assert saved.finished_at == finished_at

        async with uow:
            assert stored.id is not None
            reloaded = await repo.get_by_id(caravan_id=stored.id)
            assert reloaded is not None
            assert reloaded.status is CaravanStatus.FINISHED
            assert reloaded.finished_at == finished_at

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanRepository(uow=uow)
        ghost = Caravan(
            id=99999,
            sender_clan_id=1,
            receiver_clan_id=2,
            leader_player_id=3,
            status=CaravanStatus.LOBBY,
            started_at=NOW,
            lobby_ends_at=LOBBY_ENDS_AT,
            battle_ends_at=BATTLE_ENDS_AT,
            random_seed=1,
            finished_at=None,
        )
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost)

    @pytest.mark.asyncio
    async def test_save_without_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanRepository(uow=uow)
        ghost = Caravan.starting(
            sender_clan_id=1,
            receiver_clan_id=2,
            leader_player_id=3,
            started_at=NOW,
            lobby_ends_at=LOBBY_ENDS_AT,
            battle_ends_at=BATTLE_ENDS_AT,
            random_seed=1,
        )
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(ghost)


class TestCaravanRepositoryActiveByClan:
    @pytest.mark.asyncio
    async def test_get_active_when_none(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            assert await repo.get_active_by_clan(clan_id=999) is None

    @pytest.mark.asyncio
    async def test_get_active_returns_lobby(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        async with uow:
            active = await repo.get_active_by_clan(clan_id=sender.id)
            assert active is not None
            assert active.id == stored.id
            assert active.status is CaravanStatus.LOBBY

    @pytest.mark.asyncio
    async def test_get_active_returns_in_battle(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        async with uow:
            await repo.save(stored.mark_in_battle())

        async with uow:
            active = await repo.get_active_by_clan(clan_id=sender.id)
            assert active is not None
            assert active.status is CaravanStatus.IN_BATTLE

    @pytest.mark.asyncio
    async def test_get_active_skips_finished(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        async with uow:
            await repo.save(stored.mark_in_battle().mark_finished(finished_at=BATTLE_ENDS_AT))

        async with uow:
            assert await repo.get_active_by_clan(clan_id=sender.id) is None

    @pytest.mark.asyncio
    async def test_get_active_skips_cancelled(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )

        async with uow:
            await repo.save(stored.mark_cancelled(cancelled_at=NOW))

        async with uow:
            assert await repo.get_active_by_clan(clan_id=sender.id) is None


class TestCaravanRepositoryCooldown:
    @pytest.mark.asyncio
    async def test_last_finished_at_when_none(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            assert await repo.get_last_finished_at_for_clan(clan_id=999) is None

    @pytest.mark.asyncio
    async def test_last_finished_at_returns_max_started_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        # Старый караван — за 24 часа до текущего, уже finished.
        old_started = NOW - timedelta(hours=24)
        new_started = NOW
        async with uow:
            old_caravan = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                    started_at=old_started,
                )
            )
            await repo.save(
                old_caravan.mark_in_battle().mark_finished(
                    finished_at=old_started + timedelta(minutes=80)
                )
            )

        async with uow:
            await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                    started_at=new_started,
                )
            )

        async with uow:
            last = await repo.get_last_finished_at_for_clan(clan_id=sender.id)
            assert last is not None
            assert last == new_started

    @pytest.mark.asyncio
    async def test_last_finished_at_includes_cancelled(self, uow: SqlAlchemyUnitOfWork) -> None:
        # ГДД §9.3: кулдаун стартует с момента создания (started_at),
        # независимо от того, чем кончился предыдущий караван.
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            cancelled = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                )
            )
            await repo.save(cancelled.mark_cancelled(cancelled_at=NOW))

        async with uow:
            last = await repo.get_last_finished_at_for_clan(clan_id=sender.id)
            assert last == NOW


class TestCaravanRepositoryUniqueConstraints:
    @pytest.mark.asyncio
    async def test_one_active_caravan_per_sender_clan(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Partial-unique `uq_caravans_one_active_per_sender` гарантирует
        # «не более одного активного (LOBBY/IN_BATTLE) каравана у клана-
        # отправителя».
        sender = await _seed_clan(uow, chat_id=-100111)
        receiver_a = await _seed_clan(uow, chat_id=-100222)
        receiver_b = await _seed_clan(uow, chat_id=-100333)
        leader = await _seed_player(uow, tg_id=100)
        assert sender.id is not None
        assert receiver_a.id is not None and receiver_b.id is not None
        assert leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver_a.id,
                    leader_player_id=leader.id,
                )
            )

        with pytest.raises(DomainIntegrityError, match="failed to add caravan"):
            async with uow:
                await repo.add(
                    _new_caravan(
                        sender_clan_id=sender.id,
                        receiver_clan_id=receiver_b.id,
                        leader_player_id=leader.id,
                    )
                )

    @pytest.mark.asyncio
    async def test_finished_does_not_block_new_caravan(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Partial-unique работает только для активных статусов —
        # завершённый караван не блокирует создание нового.
        sender, receiver, leader = await _seed_clans_and_leader(uow)
        assert sender.id is not None and receiver.id is not None and leader.id is not None

        repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            old = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                    started_at=NOW - timedelta(hours=2),
                )
            )
            await repo.save(
                old.mark_in_battle().mark_finished(finished_at=NOW - timedelta(hours=1))
            )

        async with uow:
            new = await repo.add(
                _new_caravan(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                    started_at=NOW,
                )
            )
            assert new.id is not None
            assert new.id != old.id


class TestCaravanRepositoryCheckConstraints:
    @pytest.mark.asyncio
    async def test_self_target_rejected_by_db(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Доменный `__post_init__` уже не даст создать сущность с
        # `sender_clan_id == receiver_clan_id`. Дублируем низкоуровневый
        # CHECK на БД-уровне — пишем напрямую через session.execute().
        sender = await _seed_clan(uow, chat_id=-100111)
        leader = await _seed_player(uow, tg_id=100)
        assert sender.id is not None and leader.id is not None

        async with uow:
            # На сущности это бы упало в __post_init__-е; обходим через
            # raw SQL, чтобы проверить именно БД-CHECK.
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    text(
                        "INSERT INTO caravans "
                        "(sender_clan_id, receiver_clan_id, leader_player_id, "
                        "status, started_at, lobby_ends_at, battle_ends_at, "
                        "random_seed) "
                        "VALUES (:sid, :sid, :lid, 'lobby', :s, :l, :b, 1)"
                    ),
                    {
                        "sid": sender.id,
                        "lid": leader.id,
                        "s": NOW.isoformat(),
                        "l": LOBBY_ENDS_AT.isoformat(),
                        "b": BATTLE_ENDS_AT.isoformat(),
                    },
                )


# ============================================================
# CARAVAN PARTICIPANT REPOSITORY
# ============================================================


async def _seed_caravan_for_participants(
    uow: SqlAlchemyUnitOfWork,
    *,
    sender_chat_id: int = -100111,
    receiver_chat_id: int = -100222,
    leader_tg_id: int = 100,
) -> Caravan:
    sender, receiver, leader = await _seed_clans_and_leader(
        uow,
        sender_chat_id=sender_chat_id,
        receiver_chat_id=receiver_chat_id,
        leader_tg_id=leader_tg_id,
    )
    assert sender.id is not None and receiver.id is not None and leader.id is not None

    repo = SqlAlchemyCaravanRepository(uow=uow)
    async with uow:
        return await repo.add(
            _new_caravan(
                sender_clan_id=sender.id,
                receiver_clan_id=receiver.id,
                leader_player_id=leader.id,
            )
        )


class TestCaravanParticipantRepositoryCrud:
    @pytest.mark.asyncio
    async def test_list_by_caravan_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            assert await repo.list_by_caravan(caravan_id=999) == ()

    @pytest.mark.asyncio
    async def test_add_caravaneer_with_contribution(self, uow: SqlAlchemyUnitOfWork) -> None:
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        # leader-Player уже создан внутри _seed_caravan_for_participants
        leader_id = caravan.leader_player_id

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                CaravanParticipant.caravaneer(
                    caravan_id=caravan.id,
                    player_id=leader_id,
                    contribution=CaravanContribution(cm=10),
                    is_leader=True,
                    joined_at=NOW,
                )
            )
            assert stored.role is CaravanRole.CARAVANEER
            assert stored.is_leader is True
            assert stored.contribution is not None
            assert stored.contribution.cm == 10

        async with uow:
            members = await repo.list_by_caravan(caravan_id=caravan.id)
            assert len(members) == 1
            assert members[0].player_id == leader_id
            assert members[0].is_leader is True

    @pytest.mark.asyncio
    async def test_add_defender_and_raider(self, uow: SqlAlchemyUnitOfWork) -> None:
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        defender = await _seed_player(uow, tg_id=200)
        raider = await _seed_player(uow, tg_id=300)
        assert defender.id is not None and raider.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=defender.id,
                    joined_at=NOW,
                )
            )
            await repo.add(
                CaravanParticipant.raider(
                    caravan_id=caravan.id,
                    player_id=raider.id,
                    joined_at=NOW,
                )
            )

        async with uow:
            defenders = await repo.list_by_caravan_and_role(
                caravan_id=caravan.id,
                role=CaravanRole.DEFENDER,
            )
            raiders = await repo.list_by_caravan_and_role(
                caravan_id=caravan.id,
                role=CaravanRole.RAIDER,
            )
            assert len(defenders) == 1
            assert defenders[0].player_id == defender.id
            assert defenders[0].contribution is None
            assert len(raiders) == 1
            assert raiders[0].player_id == raider.id

    @pytest.mark.asyncio
    async def test_remove_existing(self, uow: SqlAlchemyUnitOfWork) -> None:
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        defender = await _seed_player(uow, tg_id=200)
        assert defender.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=defender.id,
                    joined_at=NOW,
                )
            )

        async with uow:
            await repo.remove(caravan_id=caravan.id, player_id=defender.id)

        async with uow:
            assert await repo.list_by_caravan(caravan_id=caravan.id) == ()

    @pytest.mark.asyncio
    async def test_remove_missing_is_noop(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            # Никаких exception — это идемпотентный no-op.
            await repo.remove(caravan_id=12345, player_id=67890)

    @pytest.mark.asyncio
    async def test_list_ordered_by_player_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        p1 = await _seed_player(uow, tg_id=200)
        p2 = await _seed_player(uow, tg_id=201)
        p3 = await _seed_player(uow, tg_id=202)
        assert p1.id is not None and p2.id is not None and p3.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        # Добавляем «не по порядку» — третий, первый, второй.
        async with uow:
            await repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=p3.id,
                    joined_at=NOW,
                )
            )
            await repo.add(
                CaravanParticipant.raider(
                    caravan_id=caravan.id,
                    player_id=p1.id,
                    joined_at=NOW,
                )
            )
            await repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=p2.id,
                    joined_at=NOW,
                )
            )

        async with uow:
            members = await repo.list_by_caravan(caravan_id=caravan.id)
            assert [m.player_id for m in members] == [p1.id, p2.id, p3.id]


class TestCaravanParticipantUniqueAndCheckConstraints:
    @pytest.mark.asyncio
    async def test_player_can_join_caravan_only_once(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Composite-PK `(caravan_id, player_id)` запрещает повторное
        # добавление того же игрока в один караван.
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        player = await _seed_player(uow, tg_id=200)
        assert player.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=player.id,
                    joined_at=NOW,
                )
            )

        with pytest.raises(DomainIntegrityError, match="failed to add caravan_participant"):
            async with uow:
                # Тот же player_id, другая роль — всё равно нельзя.
                await repo.add(
                    CaravanParticipant.raider(
                        caravan_id=caravan.id,
                        player_id=player.id,
                        joined_at=NOW,
                    )
                )

    @pytest.mark.asyncio
    async def test_only_one_leader_per_caravan(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Partial-unique `uq_caravan_participants_one_leader_per_caravan`:
        # `WHERE is_leader = 1` — у каравана может быть только один лидер.
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        leader_id = caravan.leader_player_id
        second = await _seed_player(uow, tg_id=200)
        assert second.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                CaravanParticipant.caravaneer(
                    caravan_id=caravan.id,
                    player_id=leader_id,
                    contribution=CaravanContribution(cm=10),
                    is_leader=True,
                    joined_at=NOW,
                )
            )

        with pytest.raises(DomainIntegrityError, match="failed to add caravan_participant"):
            async with uow:
                await repo.add(
                    CaravanParticipant.caravaneer(
                        caravan_id=caravan.id,
                        player_id=second.id,
                        contribution=CaravanContribution(cm=10),
                        is_leader=True,
                        joined_at=NOW,
                    )
                )

    @pytest.mark.asyncio
    async def test_two_caravaneers_one_leader(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Допустимо: один лидер-караванщик + не-лидер-караванщик в одном
        # караване.
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        leader_id = caravan.leader_player_id
        second = await _seed_player(uow, tg_id=200)
        assert second.id is not None

        repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await repo.add(
                CaravanParticipant.caravaneer(
                    caravan_id=caravan.id,
                    player_id=leader_id,
                    contribution=CaravanContribution(cm=10),
                    is_leader=True,
                    joined_at=NOW,
                )
            )
            await repo.add(
                CaravanParticipant.caravaneer(
                    caravan_id=caravan.id,
                    player_id=second.id,
                    contribution=CaravanContribution(cm=5),
                    is_leader=False,
                    joined_at=NOW,
                )
            )

        async with uow:
            caravaneers = await repo.list_by_caravan_and_role(
                caravan_id=caravan.id,
                role=CaravanRole.CARAVANEER,
            )
            assert len(caravaneers) == 2
            assert sum(1 for c in caravaneers if c.is_leader) == 1


class TestCaravanCascadeDelete:
    @pytest.mark.asyncio
    async def test_deleting_caravan_cascades_to_participants(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        # Хотя use-case-ы доменно не удаляют каравана (только меняют
        # status), FK ON DELETE CASCADE — last-line-of-defense на
        # случай ручной чистки или каскада с `clans`/`users`.
        caravan = await _seed_caravan_for_participants(uow)
        assert caravan.id is not None
        defender = await _seed_player(uow, tg_id=200)
        assert defender.id is not None

        participant_repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
        async with uow:
            await participant_repo.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=defender.id,
                    joined_at=NOW,
                )
            )

        # На SQLite ON DELETE CASCADE работает только при включённом
        # PRAGMA foreign_keys=ON. Включаем явно.
        async with uow:
            await uow.session.execute(text("PRAGMA foreign_keys = ON"))
            await uow.session.execute(
                text("DELETE FROM caravans WHERE id = :cid"),
                {"cid": caravan.id},
            )

        async with uow:
            assert await participant_repo.list_by_caravan(caravan_id=caravan.id) == ()
