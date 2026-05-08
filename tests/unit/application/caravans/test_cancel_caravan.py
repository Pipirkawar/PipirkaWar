"""Unit-тесты `CancelCaravan` (Спринт 3.2-D, ГДД §9.3).

Покрытие:
- happy-path: лидер отменяет караван из LOBBY → CANCELLED;
  audit `CARAVAN_CANCELLED` записан, locks снимаются у всех
  участников, lobby-close-job каравана отозван;
- идемпотентность: повторный вызов на CANCELLED → no-op,
  `was_already_cancelled=True`, audit/locks/scheduler не трогаются;
- error-cases: caravan не найден, player не найден, не лидер,
  не в LOBBY (IN_BATTLE / FINISHED).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.caravans import CancelCaravan, CaravanCancelled
from pipirik_wars.application.dto.inputs import CancelCaravanInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanContribution,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRoleConflictError,
    CaravanStatus,
    InvalidCaravanStateError,
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
    FakeDelayedJobScheduler,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=20)
_BATTLE_ENDS_AT = _LOBBY_ENDS_AT + timedelta(minutes=60)
_SENDER_CLAN_ID = 1
_RECEIVER_CLAN_ID = 2
_LEADER_TG_ID = 1001
_LEADER_PLAYER_ID = 100
_OTHER_TG_ID = 2001
_OTHER_PLAYER_ID = 200


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    CancelCaravan,
    FakeUnitOfWork,
    FakeCaravanRepository,
    FakeCaravanParticipantRepository,
    FakePlayerRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeDelayedJobScheduler,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    caravans = FakeCaravanRepository()
    participants = FakeCaravanParticipantRepository()
    players = FakePlayerRepository()
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    scheduler = FakeDelayedJobScheduler()
    used_clock = clock or FakeClock(_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    use_case = CancelCaravan(
        uow=uow,
        caravans=caravans,
        caravan_participants=participants,
        players=players,
        locks=locks,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return (
        use_case,
        uow,
        caravans,
        participants,
        players,
        lock_repo,
        audit,
        scheduler,
        used_clock,
    )


async def _seed_caravan(
    caravans: FakeCaravanRepository,
    *,
    leader_player_id: int = _LEADER_PLAYER_ID,
    status: CaravanStatus = CaravanStatus.LOBBY,
) -> Caravan:
    caravan = Caravan(
        id=None,
        sender_clan_id=_SENDER_CLAN_ID,
        receiver_clan_id=_RECEIVER_CLAN_ID,
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
    contribution_cm: int = 30,
) -> CaravanParticipant:
    leader = CaravanParticipant.caravaneer(
        caravan_id=caravan_id,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=True,
        joined_at=_NOW,
    )
    return await participants.add(leader)


async def _seed_defender_participant(
    participants: FakeCaravanParticipantRepository,
    *,
    caravan_id: int,
    player_id: int,
) -> CaravanParticipant:
    p = CaravanParticipant.defender(
        caravan_id=caravan_id,
        player_id=player_id,
        joined_at=_NOW + timedelta(minutes=1),
    )
    return await participants.add(p)


async def _acquire_player_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    now: datetime,
) -> None:
    await lock_repo.try_acquire(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.CARAVAN,
        now=now,
        expires_at=now + timedelta(minutes=80),
    )


def _input(*, caravan_id: int, tg_id: int) -> CancelCaravanInput:
    return CancelCaravanInput(caravan_id=caravan_id, tg_id=tg_id)


# ---------- Happy path ----------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_leader_cancels_from_lobby(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            lock_repo,
            _audit,
            scheduler,
            clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)
        # Лок взят на лидера (как в `CreateCaravan`).
        await _acquire_player_lock(lock_repo, player_id=leader.id, now=clock.now())

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert isinstance(result, CaravanCancelled)
        assert result.was_already_cancelled is False
        assert result.caravan.id == caravan.id
        assert result.caravan.status is CaravanStatus.CANCELLED
        # Караван сохранён в репо в статусе CANCELLED.
        stored = await caravans.get_by_id(caravan_id=caravan.id)
        assert stored is not None
        assert stored.status is CaravanStatus.CANCELLED
        # Лок лидера снят.
        assert await lock_repo.get(actor_kind="player", actor_id=leader.id) is None
        # lobby-close-job отозван.
        assert caravan.id in scheduler.cancelled_caravan_lobby_close
        # Транзакция коммитится.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_locks_released_for_all_participants(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            lock_repo,
            _audit,
            _scheduler,
            clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        defender = await _seed_player(players, tg_id=_OTHER_TG_ID, username="defender")
        assert defender.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)
        await _seed_defender_participant(participants, caravan_id=caravan.id, player_id=defender.id)
        await _acquire_player_lock(lock_repo, player_id=leader.id, now=clock.now())
        await _acquire_player_lock(lock_repo, player_id=defender.id, now=clock.now())

        await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert await lock_repo.get(actor_kind="player", actor_id=leader.id) is None
        assert await lock_repo.get(actor_kind="player", actor_id=defender.id) is None

    @pytest.mark.asyncio
    async def test_lock_release_is_noop_when_no_lock(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            lock_repo,
            _audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)
        # Лок не брался (например, истёк).
        assert await lock_repo.get(actor_kind="player", actor_id=leader.id) is None

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert result.was_already_cancelled is False
        assert result.caravan.status is CaravanStatus.CANCELLED


# ---------- Audit ----------


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_caravan_cancelled(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        defender = await _seed_player(players, tg_id=_OTHER_TG_ID, username="defender")
        assert defender.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)
        await _seed_defender_participant(participants, caravan_id=caravan.id, player_id=defender.id)

        await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CARAVAN_CANCELLED
        assert entry.actor_id == _LEADER_TG_ID
        assert entry.target_kind == "caravan"
        assert entry.target_id == str(caravan.id)
        assert entry.before is not None
        assert entry.before["status"] == CaravanStatus.LOBBY.value
        assert entry.after is not None
        assert entry.after["status"] == CaravanStatus.CANCELLED.value
        assert entry.after["participants_count"] == 2
        assert entry.after["cancelled_at"] == clock.now().isoformat()
        assert entry.idempotency_key == f"caravan_cancelled:{caravan.id}"
        assert entry.occurred_at == clock.now()


# ---------- Idempotency ----------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        (
            use_case,
            uow,
            caravans,
            _participants,
            players,
            _lock_repo,
            audit,
            scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans,
            leader_player_id=leader.id,
            status=CaravanStatus.CANCELLED,
        )
        assert caravan.id is not None

        result = await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert result.was_already_cancelled is True
        assert result.caravan.status is CaravanStatus.CANCELLED
        # Audit НЕ пишется при no-op.
        assert audit.entries == []
        # scheduler.cancel НЕ вызывается при no-op.
        assert scheduler.cancelled_caravan_lobby_close == []
        # Транзакция всё равно коммитится (выходит из `async with self._uow`).
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_double_cancel_idempotent(self) -> None:
        (
            use_case,
            _uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)

        first = await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))
        second = await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert first.was_already_cancelled is False
        assert second.was_already_cancelled is True
        # Audit-запись только одна (от первого вызова).
        assert len(audit.entries) == 1


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
            _scheduler,
            _clock,
        ) = _build_use_case()
        await _seed_player(players, tg_id=_LEADER_TG_ID)

        with pytest.raises(CaravanNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=999, tg_id=_LEADER_TG_ID))

        assert exc.value.caravan_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

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
            _scheduler,
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
    async def test_non_leader_cannot_cancel(self) -> None:
        (
            use_case,
            uow,
            caravans,
            participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        other = await _seed_player(players, tg_id=_OTHER_TG_ID, username="other")
        assert other.id is not None
        caravan = await _seed_caravan(caravans, leader_player_id=leader.id)
        assert caravan.id is not None
        await _seed_leader_participant(participants, caravan_id=caravan.id, player_id=leader.id)

        with pytest.raises(CaravanRoleConflictError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=_OTHER_TG_ID))

        assert exc.value.player_id == other.id
        assert exc.value.attempted_role == "cancel"
        assert "leader" in exc.value.reason
        assert audit.entries == []
        assert uow.rollbacks == 1
        # Караван остался в LOBBY.
        stored = await caravans.get_by_id(caravan_id=caravan.id)
        assert stored is not None
        assert stored.status is CaravanStatus.LOBBY

    @pytest.mark.asyncio
    async def test_in_battle_raises_invalid_state(self) -> None:
        (
            use_case,
            uow,
            caravans,
            _participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans,
            leader_player_id=leader.id,
            status=CaravanStatus.IN_BATTLE,
        )
        assert caravan.id is not None

        with pytest.raises(InvalidCaravanStateError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert exc.value.caravan_id == caravan.id
        assert exc.value.expected == CaravanStatus.LOBBY.value
        assert exc.value.actual == CaravanStatus.IN_BATTLE.value
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_finished_raises_invalid_state(self) -> None:
        (
            use_case,
            uow,
            caravans,
            _participants,
            players,
            _lock_repo,
            audit,
            _scheduler,
            _clock,
        ) = _build_use_case()
        leader = await _seed_player(players, tg_id=_LEADER_TG_ID)
        assert leader.id is not None
        caravan = await _seed_caravan(
            caravans,
            leader_player_id=leader.id,
            status=CaravanStatus.FINISHED,
        )
        assert caravan.id is not None

        with pytest.raises(InvalidCaravanStateError) as exc:
            await use_case.execute(_input(caravan_id=caravan.id, tg_id=_LEADER_TG_ID))

        assert exc.value.caravan_id == caravan.id
        assert exc.value.expected == CaravanStatus.LOBBY.value
        assert exc.value.actual == CaravanStatus.FINISHED.value
        assert audit.entries == []
        assert uow.rollbacks == 1
