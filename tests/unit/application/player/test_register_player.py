"""Unit-тесты `RegisterPlayer` (Спринт 1.1.3 + 1.2.4 DAU Gate)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dau import CheckDauThreshold
from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.domain.player import (
    PlayerAlreadyRegisteredError,
    PlayerStatus,
)
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.signup_queue import AlreadyQueuedError
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeDauCounter,
    FakeDauLimit,
    FakeDauThresholdAlerter,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeSignupQueueRepository,
    FakeUnitOfWork,
)


def _build_use_case(
    *,
    clock: FakeClock | None = None,
    initial_dau: int = 0,
    max_dau: int = 200,
    alerter: FakeDauThresholdAlerter | None = None,
) -> tuple[
    RegisterPlayer,
    FakePlayerRepository,
    FakeSignupQueueRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeDauCounter,
    FakeDauLimit,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    queue = FakeSignupQueueRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    counter = FakeDauCounter(initial=initial_dau)
    limit = FakeDauLimit(initial=max_dau)
    used_alerter = alerter if alerter is not None else FakeDauThresholdAlerter()
    check_threshold = CheckDauThreshold(
        uow=uow,
        dau_counter=counter,
        dau_limit=limit,
        idempotency=FakeIdempotencyKey(),
        audit=audit,
        alerter=used_alerter,
        clock=used_clock,
    )
    use_case = RegisterPlayer(
        uow=uow,
        players=players,
        signup_queue=queue,
        dau_counter=counter,
        dau_limit=limit,
        audit=audit,
        clock=used_clock,
        check_threshold=check_threshold,
    )
    return use_case, players, queue, audit, uow, used_clock, counter, limit


class TestRegisterPlayer:
    @pytest.mark.asyncio
    async def test_creates_player_with_initial_values_per_gdd_1_1(self) -> None:
        use_case, players, _queue, _audit, uow, clock, _, _ = _build_use_case()

        result = await use_case.execute(
            RegisterPlayerInput(tg_id=12345, username="alice"),
        )

        assert isinstance(result, PlayerRegistered)
        saved = result.player
        assert saved.id == 1
        assert saved.tg_id == 12345
        assert saved.length.cm == 2
        assert saved.thickness.level == 1
        assert saved.title is None
        assert saved.name is None
        assert saved.status is PlayerStatus.ACTIVE
        assert saved.username is not None
        assert saved.username.value == "alice"
        assert saved.created_at == clock.now()
        assert saved.updated_at == clock.now()
        assert len(players.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_writes_audit_entry_register(self) -> None:
        use_case, _, _, audit, _, clock, _, _ = _build_use_case()

        await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PLAYER_REGISTER
        assert entry.actor_id == 42
        assert entry.target_kind == "player"
        assert entry.target_id == "42"
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["tg_id"] == 42
        assert entry.after["length_cm"] == 2
        assert entry.after["thickness_level"] == 1
        assert entry.after["username"] is None
        assert entry.idempotency_key == "register_player:42"
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_username_none_supported(self) -> None:
        use_case, _, _, _, _, _, _, _ = _build_use_case()

        result = await use_case.execute(
            RegisterPlayerInput(tg_id=42, username=None),
        )

        assert isinstance(result, PlayerRegistered)
        assert result.player.username is None

    @pytest.mark.asyncio
    async def test_duplicate_tg_id_raises_already_registered(self) -> None:
        use_case, players, _, audit, uow, _, _, _ = _build_use_case()

        await use_case.execute(RegisterPlayerInput(tg_id=42))
        with pytest.raises(PlayerAlreadyRegisteredError) as exc_info:
            await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert exc_info.value.tg_id == 42
        assert len(players.rows) == 1
        # Первый execute → commit, второй (с raise) → rollback.
        assert uow.commits == 1
        assert uow.rollbacks == 1
        # Аудит про второй вызов не пишется.
        assert len(audit.entries) == 1

    @pytest.mark.asyncio
    async def test_record_active_called_for_registered_player(self) -> None:
        use_case, _, _, _, _, _, counter, _ = _build_use_case()

        await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert await counter.current() == 1


class TestDauGate:
    @pytest.mark.asyncio
    async def test_queued_when_dau_at_limit(self) -> None:
        # DAU = MAX_DAU → ёмкость исчерпана → в очередь.
        use_case, players, queue, _audit, uow, _clock, counter, _ = _build_use_case(
            initial_dau=2,
            max_dau=2,
        )

        result = await use_case.execute(
            RegisterPlayerInput(tg_id=999, username="bob", locale="ru"),
        )

        assert isinstance(result, PlayerQueued)
        assert result.entry.tg_id == 999
        assert result.entry.position == 1
        assert result.entry.username == "bob"
        assert result.entry.locale == "ru"
        assert result.entry.id is not None
        # В таблицу `users` ничего не попало; transaction всё равно committed
        # (пишется audit-запись PLAYER_QUEUED), но record_active не позвался.
        assert len(players.rows) == 0
        assert await queue.size() == 1
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # Очередник НЕ должен попасть в DAU — иначе он сам себя блокирует.
        assert await counter.current() == 2

    @pytest.mark.asyncio
    async def test_queued_when_dau_above_limit(self) -> None:
        use_case, _, queue, _, _, _, _, _ = _build_use_case(initial_dau=10, max_dau=2)

        result = await use_case.execute(RegisterPlayerInput(tg_id=999))

        assert isinstance(result, PlayerQueued)
        assert await queue.size() == 1

    @pytest.mark.asyncio
    async def test_queue_writes_audit_entry_player_queued(self) -> None:
        use_case, _, _, audit, _, clock, _, _ = _build_use_case(
            initial_dau=2,
            max_dau=2,
        )

        result = await use_case.execute(
            RegisterPlayerInput(tg_id=999, username="bob"),
        )
        assert isinstance(result, PlayerQueued)

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PLAYER_QUEUED
        assert entry.actor_id == 999
        assert entry.target_kind == "player"
        assert entry.target_id == "999"
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["tg_id"] == 999
        assert entry.after["position"] == 1
        assert entry.after["username"] == "bob"
        assert entry.reason == "dau_gate_full"
        assert entry.idempotency_key == "queue_player:999"
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_queue_assigns_increasing_positions(self) -> None:
        use_case, _, _, _, _, _, _, _ = _build_use_case(initial_dau=2, max_dau=2)

        first = await use_case.execute(RegisterPlayerInput(tg_id=1))
        second = await use_case.execute(RegisterPlayerInput(tg_id=2))
        third = await use_case.execute(RegisterPlayerInput(tg_id=3))

        assert isinstance(first, PlayerQueued)
        assert isinstance(second, PlayerQueued)
        assert isinstance(third, PlayerQueued)
        assert first.entry.position == 1
        assert second.entry.position == 2
        assert third.entry.position == 3

    @pytest.mark.asyncio
    async def test_double_queue_same_tg_id_raises_already_queued(self) -> None:
        use_case, _, _, audit, uow, _, _, _ = _build_use_case(initial_dau=2, max_dau=2)

        await use_case.execute(RegisterPlayerInput(tg_id=42))
        with pytest.raises(AlreadyQueuedError) as exc:
            await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert exc.value.tg_id == 42
        assert uow.commits == 1
        assert uow.rollbacks == 1
        assert len(audit.entries) == 1  # только первый PLAYER_QUEUED

    @pytest.mark.asyncio
    async def test_below_limit_registers_normally(self) -> None:
        use_case, players, queue, _, _, _, counter, _ = _build_use_case(
            initial_dau=1,
            max_dau=2,
        )

        result = await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert isinstance(result, PlayerRegistered)
        assert len(players.rows) == 1
        assert await queue.size() == 0
        assert await counter.current() == 2  # initial 1 + только что добавленный


class TestThresholdAlertHook:
    """Спринт 1.2.D: после `record_active(...)` зовём `CheckDauThreshold`."""

    @pytest.mark.asyncio
    async def test_alert_emitted_when_registration_crosses_80_percent(self) -> None:
        # MAX=10, начальный DAU=7. После регистрации станет 8 → 80%.
        alerter = FakeDauThresholdAlerter()
        use_case, _, _, audit, _, _, _, _ = _build_use_case(
            initial_dau=7,
            max_dau=10,
            alerter=alerter,
        )

        await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert len(alerter.events) == 1
        assert alerter.events[0].current_dau == 8
        assert alerter.events[0].max_dau == 10
        # Audit: PLAYER_REGISTER + DAU_THRESHOLD_REACHED.
        actions = [e.action for e in audit.entries]
        assert AuditAction.PLAYER_REGISTER in actions
        assert AuditAction.DAU_THRESHOLD_REACHED in actions

    @pytest.mark.asyncio
    async def test_no_alert_when_well_below_threshold(self) -> None:
        alerter = FakeDauThresholdAlerter()
        use_case, _, _, audit, _, _, _, _ = _build_use_case(
            initial_dau=0,
            max_dau=10,
            alerter=alerter,
        )

        await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert alerter.events == []
        actions = [e.action for e in audit.entries]
        assert AuditAction.DAU_THRESHOLD_REACHED not in actions

    @pytest.mark.asyncio
    async def test_no_alert_when_player_queued(self) -> None:
        # DAU == MAX → в очередь, никаких record_active, никакого алёрта.
        alerter = FakeDauThresholdAlerter()
        use_case, _, _, audit, _, _, _, _ = _build_use_case(
            initial_dau=2,
            max_dau=2,
            alerter=alerter,
        )

        result = await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert isinstance(result, PlayerQueued)
        assert alerter.events == []
        actions = [e.action for e in audit.entries]
        assert AuditAction.DAU_THRESHOLD_REACHED not in actions

    @pytest.mark.asyncio
    async def test_threshold_alert_only_once_per_day(self) -> None:
        # Несколько регистраций подряд после порога → 1 алёрт.
        alerter = FakeDauThresholdAlerter()
        use_case, _, _, audit, _, _, _, _ = _build_use_case(
            initial_dau=7,
            max_dau=10,
            alerter=alerter,
        )

        await use_case.execute(RegisterPlayerInput(tg_id=1))
        await use_case.execute(RegisterPlayerInput(tg_id=2))
        await use_case.execute(RegisterPlayerInput(tg_id=3))

        # Только один DAU_THRESHOLD_REACHED, хотя regs было 3.
        threshold_events = [
            e for e in audit.entries if e.action is AuditAction.DAU_THRESHOLD_REACHED
        ]
        assert len(threshold_events) == 1
        assert len(alerter.events) == 1
