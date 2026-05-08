"""Unit-тесты `FinishCaravanBattle` (Спринт 3.2-C, ГДД §9.5–§9.6).

Покрытие:

* happy-path **доставка** (auto-delivery без рейдеров): караван LOBBY-IN_BATTLE
  -> FINISHED, лидеру/караванщикам/защитникам начислены награды через
  `ILengthGranter`, кланам начислен `+1 см` каждому участнику обоих кланов,
  активити-лок снят, audit `CARAVAN_BATTLE_FINISHED` + `CARAVAN_REWARDS_GRANTED`
  записаны;
* happy-path **разграбление** (raiders win): рейдер-Атаман получает
  `Title.ATAMAN`, `TITLE_GRANT` audit-запись, погибший лидер теряет
  `unblocked_strike_damage_cm` (через прямой `with_length` + `LENGTH_REVOKE`),
  клан-бонусы НЕ начисляются;
* идемпотентность: повторный вызов на уже `FINISHED`-/`CANCELLED`-караване -
  no-op с `was_already_finished=True`, audit НЕ пишется, никаких mutations;
* инвариант: `LOBBY`-караван (job стрельнул раньше времени) -> `InvalidCaravanStateError`;
* ошибки: каравана нет -> `CaravanNotFoundError`, висячий `player_id` -> `PlayerNotFoundError`.

Зависимости: `AddLength` (реальный `ILengthGranter`) +
`FakeAnticheatRepository` -> прибавки идут через настоящий cap-trip-wire,
вычеты — прямой `Player.with_length` (см. архитектурный гард в
`tests/unit/architecture/test_length_grant_guard.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanStatus,
)
from pipirik_wars.domain.caravan.errors import InvalidCaravanStateError
from pipirik_wars.domain.clan import ClanMember, ClanMemberRole
from pipirik_wars.domain.player import (
    Player,
    PlayerNotFoundError,
    Title,
    Username,
)
from pipirik_wars.domain.security import ActivityLock, LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
    FakeClanMembershipRepository,
    FakeClock,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
_STARTED = _NOW - timedelta(minutes=80)
_LOBBY_ENDS_AT = _STARTED + timedelta(minutes=20)
_BATTLE_ENDS_AT = _STARTED + timedelta(minutes=80)

_SENDER_CLAN_ID = 10
_RECEIVER_CLAN_ID = 20

# Лидер каравана.
_LEADER_TG = 100
# Защитник.
_DEFENDER_TG = 200
# Рейдер.
_RAIDER_TG = 300

# «Чужой» член sender-клана (не участвует в бою, но получит клан-бонус).
_SENDER_BYSTANDER_TG = 110
# «Чужой» член receiver-клана.
_RECEIVER_BYSTANDER_TG = 210


def _build_use_case(
    *,
    seed: int = 1,
    clock: FakeClock | None = None,
) -> tuple[
    FinishCaravanBattle,
    FakePlayerRepository,
    FakeCaravanRepository,
    FakeCaravanParticipantRepository,
    FakeClanMembershipRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    caravans = FakeCaravanRepository()
    participants = FakeCaravanParticipantRepository()
    clan_memberships = FakeClanMembershipRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=used_clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = FinishCaravanBattle(
        uow=uow,
        caravans=caravans,
        caravan_participants=participants,
        clan_memberships=clan_memberships,
        players=players,
        length_granter=length_granter,
        locks=locks,
        audit=audit,
        clock=used_clock,
        balance=build_valid_balance().caravans,
        random_factory=lambda s: FakeRandom(seed=seed),
    )
    return (
        use_case,
        players,
        caravans,
        participants,
        clan_memberships,
        audit,
        uow,
        used_clock,
        lock_repo,
    )


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str,
) -> Player:
    return await players.add(
        Player.new(tg_id=tg_id, username=Username(value=username), now=_STARTED),
    )


async def _seed_caravan(
    caravans: FakeCaravanRepository,
    *,
    leader_player_id: int,
    status: CaravanStatus = CaravanStatus.IN_BATTLE,
    random_seed: int = 12345,
) -> Caravan:
    """Создать караван `LOBBY`/`IN_BATTLE`/`FINISHED`/`CANCELLED`.

    Для `IN_BATTLE` — переход через `mark_in_battle`. Для `FINISHED` —
    последовательно `mark_in_battle` -> `mark_finished`.
    """
    caravan = Caravan.starting(
        sender_clan_id=_SENDER_CLAN_ID,
        receiver_clan_id=_RECEIVER_CLAN_ID,
        leader_player_id=leader_player_id,
        started_at=_STARTED,
        lobby_ends_at=_LOBBY_ENDS_AT,
        battle_ends_at=_BATTLE_ENDS_AT,
        random_seed=random_seed,
    )
    saved = await caravans.add(caravan)
    if status is CaravanStatus.LOBBY:
        return saved
    if status is CaravanStatus.IN_BATTLE:
        return await caravans.save(saved.mark_in_battle())
    if status is CaravanStatus.FINISHED:
        in_battle = saved.mark_in_battle()
        return await caravans.save(in_battle.mark_finished(finished_at=_NOW))
    if status is CaravanStatus.CANCELLED:
        return await caravans.save(saved.mark_cancelled(cancelled_at=_NOW))
    raise ValueError(f"unsupported status {status!r}")


async def _seed_participant_caravaneer(
    repo: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
    is_leader: bool,
    contribution_cm: int,
) -> CaravanParticipant:
    return await repo.add(
        CaravanParticipant.caravaneer(
            caravan_id=caravan_id,
            player_id=player_id,
            contribution=CaravanContribution(cm=contribution_cm),
            is_leader=is_leader,
            joined_at=_STARTED,
        )
    )


async def _seed_participant_defender(
    repo: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
) -> CaravanParticipant:
    return await repo.add(
        CaravanParticipant.defender(
            caravan_id=caravan_id,
            player_id=player_id,
            joined_at=_STARTED,
        )
    )


async def _seed_participant_raider(
    repo: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
) -> CaravanParticipant:
    return await repo.add(
        CaravanParticipant.raider(
            caravan_id=caravan_id,
            player_id=player_id,
            joined_at=_STARTED,
        )
    )


async def _seed_clan_member(
    memberships: FakeClanMembershipRepository,
    *,
    clan_id: int,
    player_id: int,
) -> ClanMember:
    return await memberships.add(
        ClanMember.new(
            clan_id=clan_id,
            player_id=player_id,
            role=ClanMemberRole.MEMBER,
            now=_STARTED,
        )
    )


async def _seed_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    expires_at: datetime,
) -> None:
    lock_repo.locks[("player", player_id)] = ActivityLock(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.CARAVAN,
        acquired_at=_STARTED,
        expires_at=expires_at,
    )


# ---------- Happy path: delivery (no raiders) ----------


async def _assert_delivery_lengths(
    *,
    players: FakePlayerRepository,
    leader: Player,
    defender: Player,
    sender_bystander: Player,
    receiver_bystander: Player,
) -> None:
    """Длина игроков после доставки: лидер +120+1, защитник +5+1, bystander +1."""
    assert leader.id is not None
    assert defender.id is not None
    assert sender_bystander.id is not None
    assert receiver_bystander.id is not None
    leader_after = await players.get_by_id(player_id=leader.id)
    defender_after = await players.get_by_id(player_id=defender.id)
    sender_bs_after = await players.get_by_id(player_id=sender_bystander.id)
    receiver_bs_after = await players.get_by_id(player_id=receiver_bystander.id)
    assert leader_after is not None and defender_after is not None
    assert sender_bs_after is not None and receiver_bs_after is not None
    # Длина игрока стартует с _INITIAL_LENGTH_CM (Player.new). Лидер: +4×30 + 1.
    assert leader_after.length.cm == leader.length.cm + 120 + 1
    # Защитник: +1×5 (defender × base_reward_cm) + 1 (клан-бонус).
    assert defender_after.length.cm == defender.length.cm + 5 + 1
    # Bystander-ы: только клан-бонус.
    assert sender_bs_after.length.cm == sender_bystander.length.cm + 1
    assert receiver_bs_after.length.cm == receiver_bystander.length.cm + 1


def _assert_delivery_audit(*, audit: FakeAuditLogger, caravan_id: int) -> None:
    """Audit-следы доставки: 6 LENGTH_GRANT (2 бой + 4 клан-бонус) + 2 caravan-event."""
    actions = [e.action for e in audit.entries]
    assert actions.count(AuditAction.LENGTH_GRANT) == 6
    assert actions.count(AuditAction.CARAVAN_BATTLE_FINISHED) == 1
    assert actions.count(AuditAction.CARAVAN_REWARDS_GRANTED) == 1
    assert AuditAction.TITLE_GRANT not in actions
    assert AuditAction.LENGTH_REVOKE not in actions

    finished_entry = next(
        e for e in audit.entries if e.action is AuditAction.CARAVAN_BATTLE_FINISHED
    )
    assert finished_entry.target_kind == "caravan"
    assert finished_entry.target_id == str(caravan_id)
    assert finished_entry.idempotency_key == f"caravan_battle_finished:{caravan_id}"
    assert finished_entry.after is not None
    assert finished_entry.after["raiders_won"] is False
    assert finished_entry.after["status"] == CaravanStatus.FINISHED.value

    rewards_entry = next(
        e for e in audit.entries if e.action is AuditAction.CARAVAN_REWARDS_GRANTED
    )
    assert rewards_entry.idempotency_key == f"caravan_rewards_granted:{caravan_id}"
    assert rewards_entry.after is not None
    assert rewards_entry.after["total_granted_cm"] == 120 + 5
    assert rewards_entry.after["total_revoked_cm"] == 0
    # Клан-бонус: +1 × 2 (sender-клан) + 1 × 2 (receiver-клан) = 4.
    assert rewards_entry.after["clan_bonus_total_cm"] == 4
    assert rewards_entry.after["ataman_player_id"] is None


async def _setup_delivery_scenario(
    *,
    use_case: FinishCaravanBattle,
    players: FakePlayerRepository,
    caravans: FakeCaravanRepository,
    participants: FakeCaravanParticipantRepository,
    clan_memberships: FakeClanMembershipRepository,
    lock_repo: FakeActivityLockRepository,
) -> tuple[Caravan, Player, Player, Player, Player]:
    """Сидим участников: 1 лидер + 1 защитник, без рейдеров → авто-доставка."""
    del use_case  # сигнатура для совместимости с pyramid-builder
    leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
    defender = await _seed_player(players, tg_id=_DEFENDER_TG, username="defender")
    sender_bs = await _seed_player(players, tg_id=_SENDER_BYSTANDER_TG, username="sender_bs")
    receiver_bs = await _seed_player(players, tg_id=_RECEIVER_BYSTANDER_TG, username="receiver_bs")
    assert leader.id is not None
    assert defender.id is not None
    assert sender_bs.id is not None
    assert receiver_bs.id is not None

    caravan = await _seed_caravan(
        caravans,
        leader_player_id=leader.id,
        status=CaravanStatus.IN_BATTLE,
    )
    assert caravan.id is not None
    await _seed_participant_caravaneer(
        participants,
        caravan_id=caravan.id,
        player_id=leader.id,
        is_leader=True,
        contribution_cm=30,
    )
    await _seed_participant_defender(participants, caravan_id=caravan.id, player_id=defender.id)

    # Лидер + bystander в sender-клане; защитник + bystander в receiver-клане.
    await _seed_clan_member(clan_memberships, clan_id=_SENDER_CLAN_ID, player_id=leader.id)
    await _seed_clan_member(clan_memberships, clan_id=_SENDER_CLAN_ID, player_id=sender_bs.id)
    await _seed_clan_member(clan_memberships, clan_id=_RECEIVER_CLAN_ID, player_id=defender.id)
    await _seed_clan_member(clan_memberships, clan_id=_RECEIVER_CLAN_ID, player_id=receiver_bs.id)

    await _seed_lock(lock_repo, player_id=leader.id, expires_at=_BATTLE_ENDS_AT)
    await _seed_lock(lock_repo, player_id=defender.id, expires_at=_BATTLE_ENDS_AT)
    return caravan, leader, defender, sender_bs, receiver_bs


class TestHappyPathDelivery:
    """0 рейдеров -> auto-delivery, проще всего проверить детерминированно.

    Награды: лидер ×4, защитник ×base_reward; клан +1 см каждому участнику
    обоих кланов; activity-locks сняты; FINISHED + audit.
    """

    @pytest.mark.asyncio
    async def test_delivery_grants_rewards_releases_locks_and_writes_audit(
        self,
    ) -> None:
        (
            use_case,
            players,
            caravans,
            participants,
            clan_memberships,
            audit,
            uow,
            _clock,
            lock_repo,
        ) = _build_use_case(seed=1)
        caravan, leader, defender, sender_bs, receiver_bs = await _setup_delivery_scenario(
            use_case=use_case,
            players=players,
            caravans=caravans,
            participants=participants,
            clan_memberships=clan_memberships,
            lock_repo=lock_repo,
        )
        assert caravan.id is not None
        assert leader.id is not None
        assert defender.id is not None
        assert sender_bs.id is not None
        assert receiver_bs.id is not None

        result = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        assert isinstance(result, CaravanBattleFinished)
        assert result.was_already_finished is False
        assert result.caravan.status is CaravanStatus.FINISHED
        assert result.caravan.finished_at == _NOW
        assert result.result is not None
        assert result.result.raiders_won is False

        await _assert_delivery_lengths(
            players=players,
            leader=leader,
            defender=defender,
            sender_bystander=sender_bs,
            receiver_bystander=receiver_bs,
        )

        # Locks сняты.
        assert ("player", leader.id) not in lock_repo.locks
        assert ("player", defender.id) not in lock_repo.locks

        # Транзакция коммитится один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0

        _assert_delivery_audit(audit=audit, caravan_id=caravan.id)

    @pytest.mark.asyncio
    async def test_length_grant_uses_caravan_reward_source(self) -> None:
        """`AddLength` через CARAVAN_REWARD-source — anti-cheat-cap = 1.6×."""
        (
            use_case,
            players,
            caravans,
            participants,
            clan_memberships,
            audit,
            _uow,
            _clock,
            _lock_repo,
        ) = _build_use_case(seed=1)
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.IN_BATTLE
        )
        assert caravan.id is not None
        await _seed_participant_caravaneer(
            participants,
            caravan_id=caravan.id,
            player_id=leader.id,
            is_leader=True,
            contribution_cm=20,
        )
        await _seed_clan_member(clan_memberships, clan_id=_SENDER_CLAN_ID, player_id=leader.id)

        await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        # Одна LENGTH_GRANT-запись с CARAVAN_REWARD-источником и
        # idempotency-ключом `add_length:caravan_battle:{caravan.id}:{leader.id}`.
        battle_grants = [
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT
            and e.idempotency_key == f"add_length:caravan_battle:{caravan.id}:{leader.id}"
        ]
        assert len(battle_grants) == 1
        assert battle_grants[0].source is AuditSource.CARAVAN_REWARD
        assert battle_grants[0].delta_cm == 4 * 20
        # Клан-бонус — отдельная LENGTH_GRANT с другим ключом.
        clan_grants = [
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT
            and e.idempotency_key
            == f"add_length:caravan_clan_bonus:{caravan.id}:sender:{leader.id}"
        ]
        assert len(clan_grants) == 1
        assert clan_grants[0].source is AuditSource.CARAVAN_REWARD
        assert clan_grants[0].delta_cm == 1


# ---------- Happy path: raiders win + ATAMAN ----------


class TestRaidersVictory:
    """1 лидер vs 4 рейдера — почти гарантированно пробьют 2 блока."""

    async def _setup_raid(
        self,
        seed: int,
    ) -> tuple[
        FinishCaravanBattle,
        FakePlayerRepository,
        FakeCaravanRepository,
        FakeAuditLogger,
        FakeActivityLockRepository,
        Caravan,
        Player,
        list[Player],
    ]:
        (
            use_case,
            players,
            caravans,
            participants,
            clan_memberships,
            audit,
            _uow,
            _clock,
            lock_repo,
        ) = _build_use_case(seed=seed)
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        raider_players: list[Player] = []
        for i in range(4):
            r = await _seed_player(players, tg_id=_RAIDER_TG + i, username=f"raider{i}")
            assert r.id is not None
            raider_players.append(r)

        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.IN_BATTLE
        )
        assert caravan.id is not None
        await _seed_participant_caravaneer(
            participants,
            caravan_id=caravan.id,
            player_id=leader.id,
            is_leader=True,
            contribution_cm=20,
        )
        for r in raider_players:
            assert r.id is not None
            await _seed_participant_raider(participants, caravan_id=caravan.id, player_id=r.id)
        await _seed_clan_member(clan_memberships, clan_id=_SENDER_CLAN_ID, player_id=leader.id)
        await _seed_lock(lock_repo, player_id=leader.id, expires_at=_BATTLE_ENDS_AT)
        for r in raider_players:
            assert r.id is not None
            await _seed_lock(lock_repo, player_id=r.id, expires_at=_BATTLE_ENDS_AT)

        return use_case, players, caravans, audit, lock_repo, caravan, leader, raider_players

    @pytest.mark.asyncio
    async def test_raiders_win_grants_ataman_title_and_revokes_leader_length(
        self,
    ) -> None:
        for seed in range(1, 50):
            (
                use_case,
                players,
                caravans,
                audit,
                lock_repo,
                caravan,
                leader,
                raiders,
            ) = await self._setup_raid(seed=seed)
            assert caravan.id is not None
            result = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
            assert result.result is not None
            if not result.result.raiders_won:
                continue

            # Лидер мёртв -> теряет 1 см (unblocked_strike_damage_cm=1).
            assert leader.id is not None
            leader_after = await players.get_by_id(player_id=leader.id)
            assert leader_after is not None
            assert leader_after.length.cm == leader.length.cm - 1

            # Ровно один рейдер получил Title.ATAMAN.
            ataman_count = 0
            ataman_player_id: int | None = None
            for r in raiders:
                assert r.id is not None
                p = await players.get_by_id(player_id=r.id)
                assert p is not None
                if p.title is Title.ATAMAN:
                    ataman_count += 1
                    ataman_player_id = r.id
            assert ataman_count == 1

            # Audit-запись TITLE_GRANT.
            title_entries = [e for e in audit.entries if e.action is AuditAction.TITLE_GRANT]
            assert len(title_entries) == 1
            assert title_entries[0].idempotency_key == (
                f"caravan_battle_finished:title:{caravan.id}:{ataman_player_id}"
            )
            assert title_entries[0].after is not None
            assert title_entries[0].after["title"] == Title.ATAMAN.value

            # Audit-запись LENGTH_REVOKE для лидера.
            revoke_entries = [e for e in audit.entries if e.action is AuditAction.LENGTH_REVOKE]
            assert len(revoke_entries) == 1
            assert revoke_entries[0].source is AuditSource.CARAVAN_REWARD
            assert revoke_entries[0].delta_cm == -1

            # Клан-бонусы НЕ начисляются при поражении.
            rewards_entry = next(
                e for e in audit.entries if e.action is AuditAction.CARAVAN_REWARDS_GRANTED
            )
            assert rewards_entry.after is not None
            assert rewards_entry.after["clan_bonus_total_cm"] == 0
            assert rewards_entry.after["ataman_player_id"] == ataman_player_id

            # Locks сняты у всех 5 участников.
            for participant_id in (leader.id, *(r.id for r in raiders)):
                assert ("player", participant_id) not in lock_repo.locks

            # Караван FINISHED.
            assert result.caravan.status is CaravanStatus.FINISHED

            # Победа подтверждена.
            return

        pytest.fail("In 50 seeds, raiders never won a 4v1 fight — test brittle?")


# ---------- Idempotency ----------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        (
            use_case,
            players,
            caravans,
            participants,
            _memberships,
            audit,
            uow,
            _clock,
            _lock_repo,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.FINISHED
        )
        assert caravan.id is not None
        await _seed_participant_caravaneer(
            participants,
            caravan_id=caravan.id,
            player_id=leader.id,
            is_leader=True,
            contribution_cm=20,
        )

        result = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        assert result.was_already_finished is True
        assert result.result is None
        assert result.caravan.status is CaravanStatus.FINISHED
        # Никаких audit / mutations.
        assert audit.entries == []
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # Длина игрока не тронута.
        leader_after = await players.get_by_id(player_id=leader.id)
        assert leader_after is not None
        assert leader_after.length.cm == leader.length.cm

    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        (
            use_case,
            players,
            caravans,
            _participants,
            _memberships,
            audit,
            uow,
            _clock,
            _lock_repo,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.CANCELLED
        )
        assert caravan.id is not None

        result = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        assert result.was_already_finished is True
        assert result.result is None
        assert result.caravan.status is CaravanStatus.CANCELLED
        assert audit.entries == []
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_double_finish_idempotent(self) -> None:
        (
            use_case,
            players,
            caravans,
            participants,
            clan_memberships,
            audit,
            _uow,
            _clock,
            _lock_repo,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.IN_BATTLE
        )
        assert caravan.id is not None
        await _seed_participant_caravaneer(
            participants,
            caravan_id=caravan.id,
            player_id=leader.id,
            is_leader=True,
            contribution_cm=20,
        )
        await _seed_clan_member(clan_memberships, clan_id=_SENDER_CLAN_ID, player_id=leader.id)

        first = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
        second = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        assert first.was_already_finished is False
        assert second.was_already_finished is True

        # Audit-записи с CARAVAN_BATTLE_FINISHED ровно одна (от первого вызова).
        finished_entries = [
            e for e in audit.entries if e.action is AuditAction.CARAVAN_BATTLE_FINISHED
        ]
        assert len(finished_entries) == 1
        # Длина игрока не удвоилась.
        leader_after = await players.get_by_id(player_id=leader.id)
        assert leader_after is not None
        # 1 лидер без рейдеров → доставка: +4×20 + клан-бонус +1 = +81.
        assert leader_after.length.cm == leader.length.cm + 4 * 20 + 1


# ---------- Errors ----------


class TestErrors:
    @pytest.mark.asyncio
    async def test_caravan_not_found_raises(self) -> None:
        (
            use_case,
            *_rest,
            uow,
            _clock,
            _lock_repo,
        ) = _build_use_case()

        with pytest.raises(CaravanNotFoundError) as exc:
            await use_case.execute(FinishCaravanBattleInput(caravan_id=999))

        assert exc.value.caravan_id == 999
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_lobby_status_raises_invalid_state(self) -> None:
        """LOBBY-караван (job стрельнул раньше времени) → инвариант нарушен."""
        (
            use_case,
            players,
            caravans,
            _participants,
            _memberships,
            audit,
            uow,
            _clock,
            _lock_repo,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG, username="leader")
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.LOBBY
        )
        assert caravan.id is not None

        with pytest.raises(InvalidCaravanStateError) as exc:
            await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))

        assert exc.value.caravan_id == caravan.id
        assert exc.value.actual == CaravanStatus.LOBBY.value
        assert exc.value.expected == "IN_BATTLE"
        # Никаких mutations / audit.
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0
        # Караван по-прежнему LOBBY.
        stored = await caravans.get_by_id(caravan_id=caravan.id)
        assert stored is not None
        assert stored.status is CaravanStatus.LOBBY

    @pytest.mark.asyncio
    async def test_player_not_found_raises_on_revoke(self) -> None:
        """Висячая ссылка caravan_participants → players → PlayerNotFoundError.

        Тестируем именно ветку списания (рейдеры выиграли, лидер должен потерять
        длину, но игрок не существует).
        """
        for seed in range(1, 50):
            (
                use_case,
                players,
                caravans,
                participants,
                _memberships,
                audit,
                uow,
                _clock,
                _lock_repo,
            ) = _build_use_case(seed=seed)
            # 4 рейдера vs 1 «фантомного» лидера: участник в caravan_participants
            # есть, а Player-а — нет. Раидеры есть в players (чтобы Атаман-grant
            # не упал на них до того, как мы добрались до лидера-revoke).
            for i in range(4):
                await _seed_player(players, tg_id=_RAIDER_TG + i, username=f"raider{i}")

            phantom_leader_id = 99999  # игрока с таким id нет в players
            caravan = await _seed_caravan(
                caravans,
                leader_player_id=phantom_leader_id,
                status=CaravanStatus.IN_BATTLE,
            )
            assert caravan.id is not None
            await _seed_participant_caravaneer(
                participants,
                caravan_id=caravan.id,
                player_id=phantom_leader_id,
                is_leader=True,
                contribution_cm=20,
            )
            # Раидеры — реальные игроки.
            for i in range(4):
                await _seed_participant_raider(
                    participants, caravan_id=caravan.id, player_id=_RAIDER_TG + i
                )

            # Если этот seed даёт раидерам победу — попадаем в _revoke_length
            # для phantom-лидера и получаем PlayerNotFoundError.
            try:
                await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan.id))
            except PlayerNotFoundError as exc:
                assert exc.tg_id == phantom_leader_id
                assert uow.rollbacks == 1
                assert uow.commits == 0
                # CARAVAN_BATTLE_FINISHED-запись не пишется — транзакция
                # откатилась.
                assert AuditAction.CARAVAN_BATTLE_FINISHED not in [e.action for e in audit.entries]
                return
            # delivery — лидер не теряет длину, но клан-бонус идёт через
            # ILengthGranter, который тоже грузит player. Если seed дал delivery,
            # пропускаем (clan-bonus поднимет PlayerNotFoundError или LengthGrantError —
            # переходим к следующему seed).

        pytest.fail("In 50 seeds, raiders never won — cannot test phantom-revoke branch")
