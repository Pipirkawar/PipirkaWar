"""Unit-тесты `LeaveCaravanLobby` (Спринт 3.2-B, ГДД §9.3).

Покрытие:
- happy-path: участник CARAVANEER (не лидер) выходит, лок снимается,
  `returned_contribution_cm` > 0;
- участник DEFENDER выходит, `returned_contribution_cm == 0`;
- участник RAIDER выходит, `returned_contribution_cm == 0`;
- audit `CARAVAN_PLAYER_LEFT` с idempotency-key
  `caravan_player_left:{caravan_id}:{player_id}:{joined_at_iso}`;
- ошибки: caravan не найден, caravan не в LOBBY (IN_BATTLE),
  player не найден, игрок не участник, лидер не может выйти
  (отдельный `CancelCaravanLobby` в 3.2-C).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.caravans import LeaveCaravanLobby, LeftCaravanLobby
from pipirik_wars.application.dto.inputs import LeaveCaravanLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanContribution,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRole,
    CaravanRoleConflictError,
    CaravanStatus,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=20)
_BATTLE_ENDS_AT = _LOBBY_ENDS_AT + timedelta(minutes=60)
_SENDER_CLAN_ID = 1
_RECEIVER_CLAN_ID = 2
_LEADER_PLAYER_ID = 100


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    LeaveCaravanLobby,
    FakeUnitOfWork,
    FakeCaravanRepository,
    FakeCaravanParticipantRepository,
    FakePlayerRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    caravans = FakeCaravanRepository()
    participants = FakeCaravanParticipantRepository()
    players = FakePlayerRepository()
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    use_case = LeaveCaravanLobby(
        uow=uow,
        caravans=caravans,
        caravan_participants=participants,
        players=players,
        locks=locks,
        audit=audit,
        clock=used_clock,
    )
    return (
        use_case,
        uow,
        caravans,
        participants,
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
) -> Caravan:
    caravan = Caravan(
        id=None,
        sender_clan_id=sender_clan_id,
        receiver_clan_id=receiver_clan_id,
        leader_player_id=leader_player_id,
        status=CaravanStatus.LOBBY,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS_AT,
        battle_ends_at=_BATTLE_ENDS_AT,
        random_seed=12345,
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


async def _seed_caravaneer_participant(
    participants: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
    contribution_cm: int = 15,
    joined_at: datetime = _NOW,
) -> CaravanParticipant:
    p = CaravanParticipant.caravaneer(
        caravan_id=caravan_id,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=False,
        joined_at=joined_at,
    )
    return await participants.add(p)


async def _seed_defender_participant(
    participants: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
    joined_at: datetime = _NOW,
) -> CaravanParticipant:
    p = CaravanParticipant.defender(
        caravan_id=caravan_id,
        player_id=player_id,
        joined_at=joined_at,
    )
    return await participants.add(p)


async def _seed_raider_participant(
    participants: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
    joined_at: datetime = _NOW,
) -> CaravanParticipant:
    p = CaravanParticipant.raider(
        caravan_id=caravan_id,
        player_id=player_id,
        joined_at=joined_at,
    )
    return await participants.add(p)


def _input(*, caravan_id: int, tg_id: int) -> LeaveCaravanLobbyInput:
    return LeaveCaravanLobbyInput(caravan_id=caravan_id, tg_id=tg_id)


# ---------- Happy path ----------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_caravaneer_leaves_with_contribution(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            lock_repo,
            _audit,
            clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_caravaneer_participant(
            participants,
            caravan_id=caravan.id,
            player_id=joiner.id,
            contribution_cm=15,
        )
        # Лок взят на игрока (как при JoinCaravanLobby).
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=joiner.id,
            reason=LockReason.CARAVAN,
            now=clock.now(),
            expires_at=clock.now() + timedelta(minutes=80),
        )

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=200))

        assert isinstance(result, LeftCaravanLobby)
        assert result.caravan.id == caravan.id
        assert result.removed_participant.player_id == joiner.id
        assert result.removed_participant.role is CaravanRole.CARAVANEER
        assert result.returned_contribution_cm == 15
        # Участник снят, лидер остался.
        remaining = [p for p in participants.rows if p.player_id == joiner.id]
        assert remaining == []
        assert any(p.player_id == _LEADER_PLAYER_ID for p in participants.rows)
        # Лок снят.
        lock = await lock_repo.get(actor_kind="player", actor_id=joiner.id)
        assert lock is None
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_defender_leaves_with_zero_contribution(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=300)
        assert joiner.id is not None
        await _seed_defender_participant(participants, caravan_id=caravan.id, player_id=joiner.id)

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=300))

        assert result.returned_contribution_cm == 0
        assert result.removed_participant.role is CaravanRole.DEFENDER

    @pytest.mark.asyncio
    async def test_raider_leaves_with_zero_contribution(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            _lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=400)
        assert joiner.id is not None
        await _seed_raider_participant(participants, caravan_id=caravan.id, player_id=joiner.id)

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=400))

        assert result.returned_contribution_cm == 0
        assert result.removed_participant.role is CaravanRole.RAIDER

    @pytest.mark.asyncio
    async def test_lock_release_is_noop_when_no_lock(self) -> None:
        # Лок может отсутствовать (например, лок истёк или не брался).
        # `release` — идемпотентный no-op.
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            lock_repo,
            _audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=500)
        assert joiner.id is not None
        await _seed_raider_participant(participants, caravan_id=caravan.id, player_id=joiner.id)
        # Лок не брался.
        assert await lock_repo.get(actor_kind="player", actor_id=joiner.id) is None

        await use_case.execute(_input(caravan_id=caravan.id, tg_id=500))

        # И после выхода тоже нет.
        assert await lock_repo.get(actor_kind="player", actor_id=joiner.id) is None


# ---------- Audit ----------


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_caravan_player_left(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joined_at = _NOW + timedelta(minutes=2)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_caravaneer_participant(
            participants,
            caravan_id=caravan.id,
            player_id=joiner.id,
            contribution_cm=15,
            joined_at=joined_at,
        )

        await use_case.execute(_input(caravan_id=caravan.id, tg_id=200))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CARAVAN_PLAYER_LEFT
        assert entry.actor_id == 200
        assert entry.target_kind == "caravan"
        assert entry.target_id == str(caravan.id)
        assert entry.before is not None
        assert entry.before["role"] == "caravaneer"
        assert entry.before["contribution_cm"] == 15
        assert entry.before["is_leader"] is False
        assert entry.after is None
        assert entry.idempotency_key == (
            f"caravan_player_left:{caravan.id}:{joiner.id}:{joined_at.isoformat()}"
        )
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
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        await _seed_player(players, tg_id=200)

        with pytest.raises(CaravanNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=999, tg_id=200))

        assert exc.value.caravan_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_caravan_not_in_lobby_raises(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        await _seed_raider_participant(participants, caravan_id=caravan.id, player_id=joiner.id)
        # Перевели в IN_BATTLE.
        in_battle = caravan.mark_in_battle()
        await caravans.save(in_battle)

        with pytest.raises(CaravanLobbyClosedError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200))

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
            _players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=999))

        assert exc.value.tg_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_participant_raises_role_conflict(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        caravan = await _seed_caravan(caravans)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id)
        joiner = await _seed_player(players, tg_id=200)
        assert joiner.id is not None
        # Игрок зарегистрирован, но не участник.

        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=200))

        assert exc.value.player_id == joiner.id
        assert exc.value.attempted_role == "leave"
        assert "not a participant" in exc.value.reason
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_leader_cannot_leave_raises_role_conflict(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _clock,
        ) = _build_use_case()
        # Лидер с известным `tg_id`, чей `player.id` совпадёт с
        # `caravan.leader_player_id`.
        leader_player = await _seed_player(players, tg_id=42, username="leader")
        assert leader_player.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader_player.id)
        assert caravan.id is not None
        await _seed_leader_participant(
            participants,
            caravan_id=caravan.id,
            player_id=leader_player.id,
        )

        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=42))

        assert exc.value.player_id == leader_player.id
        assert exc.value.attempted_role == "leave"
        assert "leader cannot leave" in exc.value.reason
        # Участник остался.
        assert any(p.player_id == leader_player.id for p in participants.rows)
        assert audit.entries == []
        assert uow.rollbacks == 1
