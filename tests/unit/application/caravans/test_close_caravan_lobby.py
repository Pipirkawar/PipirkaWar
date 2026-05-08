"""Unit-тесты `CloseCaravanLobby` (Спринт 3.2-B, ГДД §9.3).

Покрытие:
- happy-path: караван в LOBBY → IN_BATTLE; `was_already_closed=False`,
  audit `CARAVAN_LOBBY_CLOSED` записан;
- идемпотентность: караван уже в IN_BATTLE / FINISHED / CANCELLED →
  no-op, `was_already_closed=True`, audit НЕ пишется;
- ошибка: caravan не найден → `CaravanNotFoundError`, транзакция
  откатывается.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.caravans import CloseCaravanLobby, ClosedCaravanLobby
from pipirik_wars.application.dto.inputs import CloseCaravanLobbyInput
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanNotFoundError,
    CaravanStatus,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeCaravanRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=20)
_BATTLE_ENDS_AT = _LOBBY_ENDS_AT + timedelta(minutes=60)


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    CloseCaravanLobby,
    FakeUnitOfWork,
    FakeCaravanRepository,
    FakeAuditLogger,
    FakeClock,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    caravans = FakeCaravanRepository()
    audit = FakeAuditLogger()
    scheduler = FakeDelayedJobScheduler()
    used_clock = clock or FakeClock(_NOW)
    use_case = CloseCaravanLobby(
        uow=uow,
        caravans=caravans,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return use_case, uow, caravans, audit, used_clock, scheduler


async def _seed_caravan(
    caravans: FakeCaravanRepository,
    *,
    status: CaravanStatus = CaravanStatus.LOBBY,
) -> Caravan:
    caravan = Caravan(
        id=None,
        sender_clan_id=1,
        receiver_clan_id=2,
        leader_player_id=100,
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


def _input(*, caravan_id: int) -> CloseCaravanLobbyInput:
    return CloseCaravanLobbyInput(caravan_id=caravan_id)


# ---------- Happy path ----------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_lobby_to_in_battle_transition(self) -> None:
        use_case, uow, caravans, _audit, _clock, scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.LOBBY)
        assert caravan.id is not None

        result = await use_case.execute(_input(caravan_id=caravan.id))

        assert isinstance(result, ClosedCaravanLobby)
        assert result.was_already_closed is False
        assert result.caravan.id == caravan.id
        assert result.caravan.status is CaravanStatus.IN_BATTLE
        # В репо сохранено новое состояние.
        stored = await caravans.get_by_id(caravan_id=caravan.id)
        assert stored is not None
        assert stored.status is CaravanStatus.IN_BATTLE
        # Транзакция коммитится.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # battle-finish-job запланирован на battle_ends_at.
        assert caravan.id in scheduler.scheduled_caravan_battle_finish
        scheduled = scheduler.scheduled_caravan_battle_finish[caravan.id]
        assert scheduled.run_at == result.caravan.battle_ends_at


# ---------- Audit ----------


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_caravan_lobby_closed(self) -> None:
        use_case, _uow, caravans, audit, clock, _scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.LOBBY)
        assert caravan.id is not None

        await use_case.execute(_input(caravan_id=caravan.id))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CARAVAN_LOBBY_CLOSED
        assert entry.actor_id is None
        assert entry.target_kind == "caravan"
        assert entry.target_id == str(caravan.id)
        assert entry.before is not None
        assert entry.before["status"] == CaravanStatus.LOBBY.value
        assert entry.after is not None
        assert entry.after["status"] == CaravanStatus.IN_BATTLE.value
        assert entry.idempotency_key == f"caravan_lobby_closed:{caravan.id}"
        assert entry.occurred_at == clock.now()


# ---------- Idempotency ----------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_in_battle_is_noop(self) -> None:
        use_case, uow, caravans, audit, _clock, scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.IN_BATTLE)
        assert caravan.id is not None

        result = await use_case.execute(_input(caravan_id=caravan.id))

        assert result.was_already_closed is True
        assert result.caravan.status is CaravanStatus.IN_BATTLE
        # Audit НЕ пишется при no-op.
        assert audit.entries == []
        # Транзакция всё равно коммитится (выходит из `async with self._uow`).
        assert uow.commits == 1
        # battle-finish-job НЕ планируется при no-op.
        assert scheduler.scheduled_caravan_battle_finish == {}

    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        use_case, _uow, caravans, audit, _clock, _scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.FINISHED)
        assert caravan.id is not None

        result = await use_case.execute(_input(caravan_id=caravan.id))

        assert result.was_already_closed is True
        assert result.caravan.status is CaravanStatus.FINISHED
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        use_case, _uow, caravans, audit, _clock, _scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.CANCELLED)
        assert caravan.id is not None

        result = await use_case.execute(_input(caravan_id=caravan.id))

        assert result.was_already_closed is True
        assert result.caravan.status is CaravanStatus.CANCELLED
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_double_close_idempotent(self) -> None:
        # Второй вызов на уже закрытом лобби — no-op.
        use_case, _uow, caravans, audit, _clock, _scheduler = _build_use_case()
        caravan = await _seed_caravan(caravans, status=CaravanStatus.LOBBY)
        assert caravan.id is not None

        first = await use_case.execute(_input(caravan_id=caravan.id))
        second = await use_case.execute(_input(caravan_id=caravan.id))

        assert first.was_already_closed is False
        assert second.was_already_closed is True
        # Audit-запись только одна (от первого вызова).
        assert len(audit.entries) == 1


# ---------- Errors ----------


class TestErrors:
    @pytest.mark.asyncio
    async def test_caravan_not_found_raises(self) -> None:
        use_case, uow, _caravans, audit, _clock, _scheduler = _build_use_case()

        with pytest.raises(CaravanNotFoundError) as exc:
            await use_case.execute(_input(caravan_id=999))

        assert exc.value.caravan_id == 999
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0
