"""Integration-тест `FinishCaravanBattle` (Спринт 3.2-C, ГДД §9.5–§9.6).

Проверяет полный сценарий завершения боя каравана через настоящие
SQLAlchemy-репозитории (in-memory SQLite, см. `conftest.py`):

* доставка каравана (`raiders_won=False`) — лидер ×4 от
  `contribution_cm`, защитник ×`base_reward_cm`, клан-бонус +1 см
  каждому участнику обоих кланов;
* идемпотентность: повторный вызов на уже `FINISHED`-караване —
  no-op без новых mutations;
* инвариант: `LOBBY`-караван (job стрельнул раньше) →
  :class:`InvalidCaravanStateError`.

Wiring use-case-а делается «продакшн-как-в-`bot/main.py`»:
:class:`AddLength` поверх настоящих `SqlAlchemyAnticheatRepository`
+ `SqlAlchemyAuditLogger` + `SqlAlchemyIdempotencyService`,
:class:`ActivityLockService` поверх
`SqlAlchemyActivityLockRepository`, `SeededRandom` для
детерминизма боя по `caravan.random_seed`. Только
`IAnticheatAdminAlerter` — `FakeAnticheatAdminAlerter`, потому что
его настоящая реализация — Telegram-bot-side-effect, не БД-адаптер.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pipirik_wars.application.caravans import (
    CaravanBattleFinished,
    FinishCaravanBattle,
)
from pipirik_wars.application.dto.inputs import FinishCaravanBattleInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanContribution,
    CaravanParticipant,
    CaravanStatus,
)
from pipirik_wars.domain.caravan.errors import InvalidCaravanStateError
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanMember,
    ClanTitle,
)
from pipirik_wars.domain.player import Player, Username
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.shared.ports.audit import AuditSource
from pipirik_wars.infrastructure.db.models import AuditLogORM, UserORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyActivityLockRepository,
    SqlAlchemyAnticheatRepository,
    SqlAlchemyCaravanParticipantRepository,
    SqlAlchemyCaravanRepository,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import SeededRandom
from tests.fakes import FakeAnticheatAdminAlerter, FakeBalanceConfig, FakeClock
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 8, 13, 0, 0, tzinfo=UTC)
STARTED = NOW - timedelta(minutes=80)
LOBBY_ENDS_AT = STARTED + timedelta(minutes=20)
BATTLE_ENDS_AT = STARTED + timedelta(minutes=80)
RANDOM_SEED = 12345


# -------- Seed helpers (production-like) --------


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


async def _seed_player(
    uow: SqlAlchemyUnitOfWork,
    *,
    tg_id: int,
    username: str,
) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(
            Player.new(tg_id=tg_id, username=Username(value=username), now=STARTED),
        )


async def _seed_clan_member(
    uow: SqlAlchemyUnitOfWork,
    *,
    clan_id: int,
    player_id: int,
) -> None:
    repo = SqlAlchemyClanMembershipRepository(uow=uow)
    async with uow:
        await repo.add(ClanMember.new(clan_id=clan_id, player_id=player_id, now=STARTED))


async def _seed_caravan_in_battle(
    uow: SqlAlchemyUnitOfWork,
    *,
    sender_clan_id: int,
    receiver_clan_id: int,
    leader_player_id: int,
) -> Caravan:
    """Создаёт караван и переводит его в `IN_BATTLE` (mark_in_battle через save)."""
    repo = SqlAlchemyCaravanRepository(uow=uow)
    async with uow:
        stored = await repo.add(
            Caravan.starting(
                sender_clan_id=sender_clan_id,
                receiver_clan_id=receiver_clan_id,
                leader_player_id=leader_player_id,
                started_at=STARTED,
                lobby_ends_at=LOBBY_ENDS_AT,
                battle_ends_at=BATTLE_ENDS_AT,
                random_seed=RANDOM_SEED,
            )
        )
        return await repo.save(stored.mark_in_battle())


async def _seed_participant_caravaneer(
    uow: SqlAlchemyUnitOfWork,
    *,
    caravan_id: int,
    player_id: int,
    is_leader: bool,
    contribution_cm: int,
) -> None:
    repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
    async with uow:
        await repo.add(
            CaravanParticipant.caravaneer(
                caravan_id=caravan_id,
                player_id=player_id,
                contribution=CaravanContribution(cm=contribution_cm),
                is_leader=is_leader,
                joined_at=STARTED,
            )
        )


async def _seed_participant_defender(
    uow: SqlAlchemyUnitOfWork,
    *,
    caravan_id: int,
    player_id: int,
) -> None:
    repo = SqlAlchemyCaravanParticipantRepository(uow=uow)
    async with uow:
        await repo.add(
            CaravanParticipant.defender(
                caravan_id=caravan_id,
                player_id=player_id,
                joined_at=STARTED,
            )
        )


async def _acquire_caravan_lock(
    uow: SqlAlchemyUnitOfWork,
    *,
    player_id: int,
) -> None:
    """Берём `LockReason.CARAVAN`-блок до конца боя (как `JoinCaravanLobby`)."""
    repo = SqlAlchemyActivityLockRepository(uow=uow)
    async with uow:
        await repo.try_acquire(
            actor_kind="player",
            actor_id=player_id,
            reason=LockReason.CARAVAN,
            now=STARTED,
            expires_at=BATTLE_ENDS_AT,
        )


# -------- Use-case wiring (production-like) --------


def _build_use_case(uow: SqlAlchemyUnitOfWork) -> FinishCaravanBattle:
    """Production-like wiring: настоящие SqlAlchemy-репо + AddLength + locks."""
    clock = FakeClock(NOW)
    balance = FakeBalanceConfig(build_valid_balance())
    audit_logger = SqlAlchemyAuditLogger(uow=uow)
    length_granter = AddLength(
        uow=uow,
        players=SqlAlchemyPlayerRepository(uow=uow),
        anticheat=SqlAlchemyAnticheatRepository(uow=uow),
        audit=audit_logger,
        balance=balance,
        clock=clock,
        idempotency=SqlAlchemyIdempotencyService(uow=uow),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    locks = ActivityLockService(
        repository=SqlAlchemyActivityLockRepository(uow=uow),
        clock=clock,
    )
    return FinishCaravanBattle(
        uow=uow,
        caravans=SqlAlchemyCaravanRepository(uow=uow),
        caravan_participants=SqlAlchemyCaravanParticipantRepository(uow=uow),
        clan_memberships=SqlAlchemyClanMembershipRepository(uow=uow),
        players=SqlAlchemyPlayerRepository(uow=uow),
        length_granter=length_granter,
        locks=locks,
        audit=audit_logger,
        clock=clock,
        balance=build_valid_balance().caravans,
        random_factory=SeededRandom,
    )


# -------- Tests --------


@dataclass(frozen=True, slots=True)
class _DeliverySetup:
    sender_id: int
    receiver_id: int
    leader: Player
    defender: Player
    sender_bs: Player
    receiver_bs: Player
    caravan: Caravan


async def _setup_delivery_scenario(uow: SqlAlchemyUnitOfWork) -> _DeliverySetup:
    """2 клана + 4 игрока (лидер, защитник, 2 bystander) + караван IN_BATTLE."""
    sender = await _seed_clan(uow, chat_id=-100111)
    receiver = await _seed_clan(uow, chat_id=-100222)
    assert sender.id is not None and receiver.id is not None
    leader = await _seed_player(uow, tg_id=100, username="leader")
    defender = await _seed_player(uow, tg_id=200, username="defender")
    sender_bs = await _seed_player(uow, tg_id=110, username="sender_bs")
    receiver_bs = await _seed_player(uow, tg_id=210, username="receiver_bs")
    assert leader.id is not None and defender.id is not None
    assert sender_bs.id is not None and receiver_bs.id is not None
    await _seed_clan_member(uow, clan_id=sender.id, player_id=leader.id)
    await _seed_clan_member(uow, clan_id=sender.id, player_id=sender_bs.id)
    await _seed_clan_member(uow, clan_id=receiver.id, player_id=defender.id)
    await _seed_clan_member(uow, clan_id=receiver.id, player_id=receiver_bs.id)
    caravan = await _seed_caravan_in_battle(
        uow,
        sender_clan_id=sender.id,
        receiver_clan_id=receiver.id,
        leader_player_id=leader.id,
    )
    assert caravan.id is not None
    await _seed_participant_caravaneer(
        uow,
        caravan_id=caravan.id,
        player_id=leader.id,
        is_leader=True,
        contribution_cm=30,
    )
    await _seed_participant_defender(uow, caravan_id=caravan.id, player_id=defender.id)
    await _acquire_caravan_lock(uow, player_id=leader.id)
    await _acquire_caravan_lock(uow, player_id=defender.id)
    return _DeliverySetup(
        sender_id=sender.id,
        receiver_id=receiver.id,
        leader=leader,
        defender=defender,
        sender_bs=sender_bs,
        receiver_bs=receiver_bs,
        caravan=caravan,
    )


async def _assert_delivery_db_state(
    uow: SqlAlchemyUnitOfWork,
    *,
    setup: _DeliverySetup,
) -> None:
    """Проверяет состояние БД после доставки каравана."""
    leader_id = setup.leader.id
    defender_id = setup.defender.id
    sender_bs_id = setup.sender_bs.id
    receiver_bs_id = setup.receiver_bs.id
    caravan_id = setup.caravan.id
    assert leader_id is not None and defender_id is not None
    assert sender_bs_id is not None and receiver_bs_id is not None
    assert caravan_id is not None
    async with uow:
        session = uow.session
        caravan_repo = SqlAlchemyCaravanRepository(uow=uow)
        reloaded = await caravan_repo.get_by_id(caravan_id=caravan_id)
        assert reloaded is not None
        assert reloaded.status is CaravanStatus.FINISHED
        assert reloaded.finished_at == NOW
        # users.length_cm: лидер +120+1, защитник +5+1, bystander-ы +1.
        leader_after = await session.scalar(
            select(UserORM.length_cm).where(UserORM.id == leader_id),
        )
        defender_after = await session.scalar(
            select(UserORM.length_cm).where(UserORM.id == defender_id),
        )
        sender_bs_after = await session.scalar(
            select(UserORM.length_cm).where(UserORM.id == sender_bs_id),
        )
        receiver_bs_after = await session.scalar(
            select(UserORM.length_cm).where(UserORM.id == receiver_bs_id),
        )
        assert leader_after == setup.leader.length.cm + 120 + 1
        assert defender_after == setup.defender.length.cm + 5 + 1
        assert sender_bs_after == setup.sender_bs.length.cm + 1
        assert receiver_bs_after == setup.receiver_bs.length.cm + 1
        # audit_log: 1× CARAVAN_BATTLE_FINISHED + 1× CARAVAN_REWARDS_GRANTED
        # + 6× LENGTH_GRANT (2 бой + 4 клан-бонус).
        assert (
            await _count_audit(
                session,
                action=AuditAction.CARAVAN_BATTLE_FINISHED.value,
                target_id=str(caravan_id),
            )
            == 1
        )
        assert (
            await _count_audit(
                session,
                action=AuditAction.CARAVAN_REWARDS_GRANTED.value,
                target_id=str(caravan_id),
            )
            == 1
        )
        assert (
            await _count_audit(
                session,
                action=AuditAction.LENGTH_GRANT.value,
                source=AuditSource.CARAVAN_REWARD.value,
            )
            == 6
        )
        # activity_locks сняты для обоих участников боя.
        lock_repo = SqlAlchemyActivityLockRepository(uow=uow)
        assert await lock_repo.get(actor_kind="player", actor_id=leader_id) is None
        assert await lock_repo.get(actor_kind="player", actor_id=defender_id) is None


async def _count_audit(
    session: AsyncSession,
    *,
    action: str,
    target_id: str | None = None,
    source: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AuditLogORM).where(AuditLogORM.action == action)
    if target_id is not None:
        stmt = stmt.where(AuditLogORM.target_id == target_id)
    if source is not None:
        stmt = stmt.where(AuditLogORM.source == source)
    result = await session.scalar(stmt)
    return int(result or 0)


class TestFinishCaravanBattleDelivery:
    """Auto-delivery (0 рейдеров) — детерминистичный happy-path."""

    @pytest.mark.asyncio
    async def test_delivery_finishes_caravan_grants_rewards_releases_locks(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Полный сценарий доставки каравана через настоящие репозитории.

        Сценарий:
        * 2 клана (sender, receiver), 1 лидер + 1 защитник + 2
          bystander-участника кланов (без участия в бою).
        * Караван в `IN_BATTLE` без рейдеров — гарантированный delivery.
        * После `FinishCaravanBattle.execute()`:
            - `caravans.status = FINISHED`, `finished_at = NOW`;
            - `users.length_cm`: лидер +120+1, защитник +5+1, bystander-ы +1;
            - в `audit_log`: `CARAVAN_BATTLE_FINISHED` + `CARAVAN_REWARDS_GRANTED`
              + 6× `LENGTH_GRANT` (2 из боя + 4 клан-бонус);
            - `activity_locks` сняты для обоих участников боя.
        """
        setup = await _setup_delivery_scenario(uow)
        assert setup.caravan.id is not None

        use_case = _build_use_case(uow)
        result = await use_case.execute(FinishCaravanBattleInput(caravan_id=setup.caravan.id))

        assert isinstance(result, CaravanBattleFinished)
        assert result.was_already_finished is False
        assert result.caravan.status is CaravanStatus.FINISHED
        assert result.caravan.finished_at == NOW
        assert result.result is not None
        assert result.result.raiders_won is False

        await _assert_delivery_db_state(uow, setup=setup)


class TestFinishCaravanBattleIdempotency:
    """Повторный вызов на уже `FINISHED` — no-op (без mutations и audit-записей)."""

    @pytest.mark.asyncio
    async def test_double_finish_is_idempotent(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        sender = await _seed_clan(uow, chat_id=-100111)
        receiver = await _seed_clan(uow, chat_id=-100222)
        assert sender.id is not None and receiver.id is not None

        leader = await _seed_player(uow, tg_id=100, username="leader")
        assert leader.id is not None
        await _seed_clan_member(uow, clan_id=sender.id, player_id=leader.id)

        caravan = await _seed_caravan_in_battle(
            uow,
            sender_clan_id=sender.id,
            receiver_clan_id=receiver.id,
            leader_player_id=leader.id,
        )
        assert caravan.id is not None
        await _seed_participant_caravaneer(
            uow,
            caravan_id=caravan.id,
            player_id=leader.id,
            is_leader=True,
            contribution_cm=20,
        )

        use_case = _build_use_case(uow)
        first = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
        assert first.was_already_finished is False

        # Захолдим counts после первого вызова.
        async with uow:
            session = uow.session
            audit_count_after_first = await session.scalar(
                select(func.count()).select_from(AuditLogORM),
            )
            length_after_first = await session.scalar(
                select(UserORM.length_cm).where(UserORM.id == leader.id),
            )

        # Второй вызов — no-op (статус уже FINISHED).
        second = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
        assert second.was_already_finished is True
        assert second.result is None
        assert second.caravan.status is CaravanStatus.FINISHED

        async with uow:
            session = uow.session
            audit_count_after_second = await session.scalar(
                select(func.count()).select_from(AuditLogORM),
            )
            length_after_second = await session.scalar(
                select(UserORM.length_cm).where(UserORM.id == leader.id),
            )

        # Никаких новых audit-записей и mutations длины.
        assert audit_count_after_second == audit_count_after_first
        assert length_after_second == length_after_first


class TestFinishCaravanBattleInvariants:
    """LOBBY-караван (job стрельнул раньше) → `InvalidCaravanStateError`."""

    @pytest.mark.asyncio
    async def test_lobby_status_raises_invalid_state(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        sender = await _seed_clan(uow, chat_id=-100111)
        receiver = await _seed_clan(uow, chat_id=-100222)
        assert sender.id is not None and receiver.id is not None
        leader = await _seed_player(uow, tg_id=100, username="leader")
        assert leader.id is not None

        # Караван в LOBBY (без `mark_in_battle`).
        caravan_repo = SqlAlchemyCaravanRepository(uow=uow)
        async with uow:
            caravan = await caravan_repo.add(
                Caravan.starting(
                    sender_clan_id=sender.id,
                    receiver_clan_id=receiver.id,
                    leader_player_id=leader.id,
                    started_at=STARTED,
                    lobby_ends_at=LOBBY_ENDS_AT,
                    battle_ends_at=BATTLE_ENDS_AT,
                    random_seed=RANDOM_SEED,
                )
            )
        assert caravan.id is not None
        assert caravan.status is CaravanStatus.LOBBY

        use_case = _build_use_case(uow)
        with pytest.raises(InvalidCaravanStateError) as exc:
            await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
        assert exc.value.expected == "IN_BATTLE"
        assert exc.value.actual == CaravanStatus.LOBBY.value
