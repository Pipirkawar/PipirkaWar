"""Unit-тесты `JoinCaravanLobby` (Спринт 3.2-B, ГДД §9.4 — §9.5).

Покрытие:
- happy-path для трёх ролей: CARAVANEER (член sender), DEFENDER (член
  receiver), RAIDER (не в обоих кланах);
- audit `CARAVAN_PLAYER_JOINED` с idempotency-key;
- лок берётся с `LockReason.CARAVAN`;
- ошибки: caravan не найден, caravan не в LOBBY, player не найден,
  player заморожен, уже участник, role-conflict-ы (5 кейсов §9.4),
  thickness < 5 для RAIDER, length < 20 (DEFENDER/RAIDER), length
  после взноса < 20 (CARAVANEER), capacity для RAIDER, capacity для
  DEFENDER, лок уже взят.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.caravans import JoinCaravanLobby, JoinedCaravanLobby
from pipirik_wars.application.dto.inputs import JoinCaravanLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    Caravan,
    CaravanCapacityExceededError,
    CaravanContribution,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRequirementError,
    CaravanRole,
    CaravanRoleConflictError,
    CaravanStatus,
)
from pipirik_wars.domain.clan import (
    ClanMember,
    ClanMemberRole,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
    FakeClanMembershipRepository,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_BATTLE_MINUTES = 60
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=_LOBBY_MINUTES)
_BATTLE_ENDS_AT = _LOBBY_ENDS_AT + timedelta(minutes=_BATTLE_MINUTES)
_SENDER_CLAN_ID = 1
_RECEIVER_CLAN_ID = 2
_THIRD_CLAN_ID = 3
_LEADER_PLAYER_ID = 100
_LEADER_TG_ID = 42


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    JoinCaravanLobby,
    FakeUnitOfWork,
    FakeCaravanRepository,
    FakeCaravanParticipantRepository,
    FakeClanMembershipRepository,
    FakePlayerRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    caravans = FakeCaravanRepository()
    participants = FakeCaravanParticipantRepository()
    members = FakeClanMembershipRepository()
    players = FakePlayerRepository()
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    use_case = JoinCaravanLobby(
        uow=uow,
        caravans=caravans,
        caravan_participants=participants,
        clan_members=members,
        players=players,
        locks=locks,
        balance=balance,
        audit=audit,
        clock=used_clock,
    )
    return (
        use_case,
        uow,
        caravans,
        participants,
        members,
        players,
        lock_repo,
        audit,
        used_clock,
    )


async def _seed_caravan(
    caravans: FakeCaravanRepository,
    *,
    sender_clan_id: int = _SENDER_CLAN_ID,
    receiver_clan_id: int = _RECEIVER_CLAN_ID,
    leader_player_id: int = _LEADER_PLAYER_ID,
    status: CaravanStatus = CaravanStatus.LOBBY,
    started_at: datetime = _NOW,
    lobby_ends_at: datetime = _LOBBY_ENDS_AT,
    battle_ends_at: datetime = _BATTLE_ENDS_AT,
    random_seed: int = 12345,
) -> Caravan:
    caravan = Caravan(
        id=None,
        sender_clan_id=sender_clan_id,
        receiver_clan_id=receiver_clan_id,
        leader_player_id=leader_player_id,
        status=CaravanStatus.LOBBY,
        started_at=started_at,
        lobby_ends_at=lobby_ends_at,
        battle_ends_at=battle_ends_at,
        random_seed=random_seed,
        finished_at=None,
    )
    saved = await caravans.add(caravan)
    if status is CaravanStatus.LOBBY:
        return saved
    if status is CaravanStatus.IN_BATTLE:
        return await caravans.save(saved.mark_in_battle())
    if status is CaravanStatus.FINISHED:
        return await caravans.save(
            saved.mark_in_battle().mark_finished(finished_at=_BATTLE_ENDS_AT)
        )
    if status is CaravanStatus.CANCELLED:
        return await caravans.save(saved.mark_cancelled(cancelled_at=_NOW))
    raise ValueError(f"unsupported status {status!r}")


async def _seed_leader_participant(
    participants: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int = _LEADER_PLAYER_ID,
    contribution_cm: int = 10,
    joined_at: datetime = _NOW,
) -> CaravanParticipant:
    leader = CaravanParticipant.caravaneer(
        caravan_id=caravan_id,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=True,
        joined_at=joined_at,
    )
    return await participants.add(leader)


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str = "user",
    length_cm: int = 100,
    thickness_level: int = 7,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


async def _seed_member(
    members: FakeClanMembershipRepository,
    *,
    clan_id: int,
    player_id: int,
    role: ClanMemberRole = ClanMemberRole.MEMBER,
) -> ClanMember:
    fresh = ClanMember.new(clan_id=clan_id, player_id=player_id, role=role, now=_NOW)
    return await members.add(fresh)


def _input(
    *,
    caravan_id: int = 1,
    tg_id: int,
    role: str,
    contribution_cm: int | None = None,
) -> JoinCaravanLobbyInput:
    return JoinCaravanLobbyInput(
        caravan_id=caravan_id,
        tg_id=tg_id,
        role=role,  # type: ignore[arg-type]
        contribution_cm=contribution_cm,
    )


async def _seed_default_caravan(
    *,
    caravans: FakeCaravanRepository,
    participants: FakeCaravanParticipantRepository,
) -> Caravan:
    caravan = await _seed_caravan(caravans)
    assert caravan.id is not None
    await _seed_leader_participant(participants, caravan_id=caravan.id)
    return caravan


# ---------- Happy path ----------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_caravaneer_member_of_sender_joins(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, length_cm=100, thickness_level=3)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        result = await use_case.execute(
            _input(
                caravan_id=caravan.id,
                tg_id=200,
                role="caravaneer",
                contribution_cm=15,
            )
        )

        assert isinstance(result, JoinedCaravanLobby)
        assert len(participants.rows) == 2
        joined = participants.rows[1]
        assert joined.role is CaravanRole.CARAVANEER
        assert joined.is_leader is False
        assert joined.contribution is not None
        assert joined.contribution.cm == 15
        assert joined.player_id == joiner.id
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_defender_member_of_receiver_joins(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=300)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_RECEIVER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=300, role="defender"))

        assert isinstance(result, JoinedCaravanLobby)
        joined = result.participant
        assert joined.role is CaravanRole.DEFENDER
        assert joined.is_leader is False
        assert joined.contribution is None
        assert joined.player_id == joiner.id

    @pytest.mark.asyncio
    async def test_raider_no_clan_joins(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            _members,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=400, thickness_level=5)
        assert joiner.id is not None
        # Игрок не в клане.

        assert caravan.id is not None
        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=400, role="raider"))

        assert isinstance(result, JoinedCaravanLobby)
        joined = result.participant
        assert joined.role is CaravanRole.RAIDER
        assert joined.is_leader is False
        assert joined.contribution is None
        assert joined.player_id == joiner.id

    @pytest.mark.asyncio
    async def test_raider_in_third_clan_joins(self) -> None:
        # Игрок в третьем (не sender и не receiver) клане — может быть RAIDER.
        (
            use_case,
            _uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=500, thickness_level=5)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_THIRD_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=500, role="raider"))

        assert result.participant.role is CaravanRole.RAIDER

    @pytest.mark.asyncio
    async def test_lock_taken_with_caravan_reason(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            members,
            players,
            lock_repo,
            _audit,
            clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        await use_case.execute(
            _input(
                caravan_id=caravan.id,
                tg_id=200,
                role="caravaneer",
                contribution_cm=10,
            )
        )

        lock = await lock_repo.get(actor_kind="player", actor_id=joiner.id)
        assert lock is not None
        assert lock.reason is LockReason.CARAVAN
        # TTL должен покрывать как минимум до конца боя.
        assert lock.expires_at >= caravan.battle_ends_at
        # И не раньше, чем `now + battle_minutes`.
        minimum_ttl_end = clock.now() + timedelta(minutes=_BATTLE_MINUTES)
        assert lock.expires_at >= minimum_ttl_end


# ---------- Audit ----------


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_caravan_player_joined(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, length_cm=100)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        await use_case.execute(
            _input(
                caravan_id=caravan.id,
                tg_id=200,
                role="caravaneer",
                contribution_cm=15,
            )
        )

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CARAVAN_PLAYER_JOINED
        assert entry.actor_id == 200
        assert entry.target_kind == "caravan"
        assert entry.target_id == str(caravan.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["caravan_id"] == caravan.id
        assert entry.after["player_id"] == joiner.id
        assert entry.after["role"] == "caravaneer"
        assert entry.after["contribution_cm"] == 15
        assert entry.idempotency_key == f"caravan_player_joined:{caravan.id}:{joiner.id}"
        assert entry.occurred_at == clock.now()


# ---------- Errors ----------


class TestErrors:
    @pytest.mark.asyncio
    async def test_caravan_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            _caravans,
            _participants,
            _members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        await _seed_player(players, tg_id=200)

        with pytest.raises(CaravanNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=999, tg_id=200, role="raider"))

        assert exc.value.caravan_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_caravan_in_battle_raises_lobby_closed(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.LOBBY)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        # Перевести вручную в IN_BATTLE.
        await caravans.save(caravan.mark_in_battle())
        await _seed_player(players, tg_id=200, thickness_level=5)

        with pytest.raises(CaravanLobbyClosedError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.caravan_id == caravan.id
        assert exc.value.status == CaravanStatus.IN_BATTLE.value
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            _players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)

        assert caravan.id is not None
        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=999, role="raider"))

        assert exc.value.tg_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_frozen_raises(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)
        frozen = joiner.freeze(now=_NOW)
        await players.save(frozen)

        assert caravan.id is not None
        with pytest.raises(PlayerFrozenError) as exc:
            await use_case.execute(
                _input(
                    caravan_id=caravan.id,
                    tg_id=200,
                    role="caravaneer",
                    contribution_cm=10,
                )
            )

        assert exc.value.tg_id == 200
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_already_participant_raises(self) -> None:
        # Лидер каравана уже CARAVANEER → не может вступить второй раз
        # (даже как DEFENDER, но это RoleConflict; здесь — повторный
        # вход той же ролью).
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        # Игрок-лидер уже в участниках. Сидим его как Player + LEADER в sender_clan.
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        # Используем заранее заданный leader_player_id из caravan.
        # Поскольку `_seed_player` назначает id автоинкрементом (1),
        # а у участника-лидера id=_LEADER_PLAYER_ID (100), нужен матч.
        # Поэтому пересоздадим caravan под актуальный leader.id.
        caravans.rows.clear()
        participants.rows.clear()
        caravan = await _seed_caravan(
            caravans, leader_player_id=leader.id, status=CaravanStatus.LOBBY
        )
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)
        await _seed_member(
            members,
            clan_id=_SENDER_CLAN_ID,
            player_id=leader.id,
            role=ClanMemberRole.LEADER,
        )

        with pytest.raises(AlreadyInCaravanError) as exc:
            await use_case.execute(
                _input(
                    caravan_id=caravan.id,
                    tg_id=_LEADER_TG_ID,
                    role="caravaneer",
                    contribution_cm=5,
                )
            )

        assert exc.value.player_id == leader.id
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_caravaneer_not_in_sender_clan_raises_role_conflict(self) -> None:
        # §9.4: CARAVANEER должен быть в sender_clan.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        # Игрок в receiver_clan, а пытается зайти как CARAVANEER.
        await _seed_member(members, clan_id=_RECEIVER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(
                _input(
                    caravan_id=caravan.id,
                    tg_id=200,
                    role="caravaneer",
                    contribution_cm=10,
                )
            )

        assert exc.value.player_id == joiner.id
        assert exc.value.attempted_role == "caravaneer"
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_defender_not_in_receiver_clan_raises_role_conflict(self) -> None:
        # §9.4: DEFENDER должен быть в receiver_clan.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        # Игрок в sender_clan, а пытается зайти как DEFENDER.
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="defender"))

        assert exc.value.attempted_role == "defender"
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_raider_member_of_sender_clan_raises_role_conflict(self) -> None:
        # §9.4: RAIDER не должен быть ни в sender, ни в receiver.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, thickness_level=5)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.attempted_role == "raider"
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_raider_member_of_receiver_clan_raises_role_conflict(self) -> None:
        # §9.4: RAIDER не должен быть в receiver.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, thickness_level=5)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_RECEIVER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.attempted_role == "raider"
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_raider_thickness_below_required_raises(self) -> None:
        # §9.5: RAIDER требует thickness_level >= min_thickness_level_raider (5).
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, thickness_level=4)
        assert joiner.id is not None

        assert caravan.id is not None
        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 5
        assert exc.value.actual == 4
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_caravaneer_length_after_contribution_below_required_raises(self) -> None:
        # §9.2: у CARAVANEER `length - contribution_cm >= 20`.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        # length 25, contribution 10 → remaining 15 < 20.
        joiner = await _seed_player(players, tg_id=200, length_cm=25)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_SENDER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(
                _input(
                    caravan_id=caravan.id,
                    tg_id=200,
                    role="caravaneer",
                    contribution_cm=10,
                )
            )

        assert exc.value.requirement == "length_after_contribution"
        assert exc.value.required == 20
        assert exc.value.actual == 15
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_defender_length_below_required_raises(self) -> None:
        # §9.2: у DEFENDER `length >= 20`.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, length_cm=15)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_RECEIVER_CLAN_ID, player_id=joiner.id)

        assert caravan.id is not None
        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="defender"))

        assert exc.value.requirement == "length_total"
        assert exc.value.required == 20
        assert exc.value.actual == 15
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_raider_length_below_required_raises(self) -> None:
        # §9.2: у RAIDER `length >= 20`. Толщину поднимем до проходной.
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, length_cm=15, thickness_level=5)
        assert joiner.id is not None

        assert caravan.id is not None
        with pytest.raises(CaravanRequirementError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.requirement == "length_total"
        assert exc.value.required == 20
        assert exc.value.actual == 15
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_capacity_exceeded_for_raiders_raises(self) -> None:
        # §9.5: RAIDER count <= max_raiders_per_caravaneer (4) × CARAVANEER count.
        # 1 лидер-CARAVANEER → cap=4. После 4 рейдеров пятый отваливается.
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        assert caravan.id is not None
        # Засеять 4 рейдеров напрямую через repo.
        for i in range(4):
            await participants.add(
                CaravanParticipant.raider(
                    caravan_id=caravan.id,
                    player_id=300 + i,
                    joined_at=_NOW,
                )
            )
        joiner = await _seed_player(players, tg_id=200, thickness_level=5)
        assert joiner.id is not None

        with pytest.raises(CaravanCapacityExceededError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.caravan_id == caravan.id
        assert exc.value.role == "raider"
        assert exc.value.limit == 4
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_capacity_exceeded_for_defenders_raises(self) -> None:
        # §9.5: DEFENDER count <= max_defenders_per_caravaneer (2) × CARAVANEER.
        (
            use_case,
            uow,
            caravans,
            participants,
            members,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        assert caravan.id is not None
        # 2 защитника уже есть.
        for i in range(2):
            await participants.add(
                CaravanParticipant.defender(
                    caravan_id=caravan.id,
                    player_id=400 + i,
                    joined_at=_NOW,
                )
            )
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_member(members, clan_id=_RECEIVER_CLAN_ID, player_id=joiner.id)

        with pytest.raises(CaravanCapacityExceededError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="defender"))

        assert exc.value.role == "defender"
        assert exc.value.limit == 2
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_lock_already_held_raises_already_in_caravan(self) -> None:
        # Игрок уже занят в другой активности (FOREST), пытается войти в караван.
        (
            use_case,
            uow,
            caravans,
            participants,
            _members,
            players,
            lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        caravan = await _seed_default_caravan(caravans=caravans, participants=participants)
        joiner = await _seed_player(players, tg_id=200, thickness_level=5)
        assert joiner.id is not None
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=joiner.id,
            reason=LockReason.FOREST,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=30),
        )

        assert caravan.id is not None
        with pytest.raises(AlreadyInCaravanError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200, role="raider"))

        assert exc.value.player_id == joiner.id
        assert audit.entries == []
        assert uow.rollbacks == 1
