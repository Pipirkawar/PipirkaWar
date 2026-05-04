"""Unit-тесты `CheckDauThreshold` (Спринт 1.2.D, ГДД §8.3 / 1.2.7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dau import (
    DAU_THRESHOLD_NAMESPACE,
    DAU_THRESHOLD_PERCENT,
    CheckDauThreshold,
)
from pipirik_wars.application.dau.check_threshold import (
    CheckDauThresholdResult,
    _is_threshold_reached,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeDauCounter,
    FakeDauLimit,
    FakeDauThresholdAlerter,
    FakeIdempotencyKey,
    FakeUnitOfWork,
)

_BASE_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def _build(
    *,
    initial_dau: int = 0,
    max_dau: int = 10,
    clock: FakeClock | None = None,
) -> tuple[
    CheckDauThreshold,
    FakeUnitOfWork,
    FakeAuditLogger,
    FakeIdempotencyKey,
    FakeDauThresholdAlerter,
    FakeDauCounter,
    FakeDauLimit,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    audit = FakeAuditLogger()
    idempotency = FakeIdempotencyKey()
    alerter = FakeDauThresholdAlerter()
    counter = FakeDauCounter(initial=initial_dau)
    limit = FakeDauLimit(initial=max_dau)
    used_clock = clock or FakeClock(_BASE_NOW)
    use_case = CheckDauThreshold(
        uow=uow,
        dau_counter=counter,
        dau_limit=limit,
        idempotency=idempotency,
        audit=audit,
        alerter=alerter,
        clock=used_clock,
    )
    return use_case, uow, audit, idempotency, alerter, counter, limit, used_clock


class TestIsThresholdReached:
    @pytest.mark.parametrize(
        ("current", "max_dau", "expected"),
        [
            (0, 10, False),  # 0% < 80%
            (7, 10, False),  # 70% < 80%
            (8, 10, True),  # 80% == 80%
            (9, 10, True),  # 90% > 80%
            (10, 10, True),  # 100% — overflow, тоже алёрт
            (4, 5, True),  # 80% точно — int math
            (3, 5, False),  # 60%
            (1, 1, True),  # MAX=1 → один игрок = алёрт
            (0, 1, False),
            # Граница округления: 4 / 6 ≈ 66.7% < 80%, 5 / 6 ≈ 83.3% >= 80%.
            (4, 6, False),
            (5, 6, True),
        ],
    )
    def test_threshold_check(
        self,
        *,
        current: int,
        max_dau: int,
        expected: bool,
    ) -> None:
        assert _is_threshold_reached(current=current, max_dau=max_dau) is expected


class TestCheckDauThreshold:
    @pytest.mark.asyncio
    async def test_below_threshold_does_nothing(self) -> None:
        use_case, uow, audit, idem, alerter, _c, _l, _ = _build(initial_dau=5, max_dau=10)

        result = await use_case.execute()

        assert result == CheckDauThresholdResult(triggered=False, current_dau=5, max_dau=10)
        assert result.percent == 50
        assert audit.entries == []
        assert alerter.events == []
        assert (
            uow.commits == 0
        )  # \u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446\u0438\u044e \u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u043b\u0438
        # idempotency-\u043a\u043b\u044e\u0447 \u043d\u0435 \u0442\u0440\u043e\u0433\u0430\u043b\u0438
        assert not await idem.is_seen(idem.build(DAU_THRESHOLD_NAMESPACE, ["any"]))

    @pytest.mark.asyncio
    async def test_first_crossing_writes_audit_and_emits_alert(self) -> None:
        use_case, uow, audit, idem, alerter, _c, _l, clock = _build(initial_dau=8, max_dau=10)

        result = await use_case.execute()

        assert result.triggered is True
        assert result.current_dau == 8
        assert result.max_dau == 10
        assert result.percent == 80
        # \u0410\u0443\u0434\u0438\u0442 \u0438 idempotency \u0432 \u043e\u0434\u043d\u043e\u0439 \u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446\u0438\u0438.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.DAU_THRESHOLD_REACHED
        assert entry.actor_id is None
        assert entry.target_kind == "dau"
        assert entry.target_id == clock.moscow_date().isoformat()
        assert entry.before is None
        assert entry.after == {
            "current_dau": 8,
            "max_dau": 10,
            "percent": DAU_THRESHOLD_PERCENT,
        }
        assert entry.reason == "dau_threshold_alert"
        expected_key = f"{DAU_THRESHOLD_NAMESPACE}:{clock.moscow_date().isoformat()}"
        assert entry.idempotency_key == expected_key
        assert entry.occurred_at == clock.now()
        # \u0410\u043b\u0451\u0440\u0442 \u0443\u0448\u0451\u043b \u043f\u043e\u0441\u043b\u0435 \u043a\u043e\u043c\u043c\u0438\u0442\u0430.
        assert len(alerter.events) == 1
        event = alerter.events[0]
        assert event.current_dau == 8
        assert event.max_dau == 10
        assert event.percent == DAU_THRESHOLD_PERCENT
        assert event.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_second_call_same_day_is_noop(self) -> None:
        use_case, uow, audit, _idem, alerter, _c, _l, _ = _build(initial_dau=8, max_dau=10)

        first = await use_case.execute()
        second = await use_case.execute()

        assert first.triggered is True
        assert second.triggered is False
        # \u0410\u0443\u0434\u0438\u0442 \u0440\u043e\u0432\u043d\u043e \u043e\u0434\u0438\u043d.
        assert len(audit.entries) == 1
        assert len(alerter.events) == 1
        # \u0412\u0442\u043e\u0440\u0430\u044f \u0442\u0440\u0430\u043d\u0437\u0430\u043a\u0446\u0438\u044f \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u043b\u0430\u0441\u044c (\u0434\u043b\u044f is_seen), \u043d\u043e \u043d\u0435 \u043f\u0438\u0441\u0430\u043b\u0430.
        assert uow.commits == 2

    @pytest.mark.asyncio
    async def test_new_day_resets_idempotency(self) -> None:
        clock = FakeClock(_BASE_NOW)
        use_case, _uow, audit, _idem, alerter, _c, _l, _ = _build(
            initial_dau=8, max_dau=10, clock=clock
        )

        first = await use_case.execute()
        # \u0421\u0434\u0432\u0438\u0433\u0430\u0435\u043c \u0432\u0440\u0435\u043c\u044f \u043d\u0430 \u0441\u0443\u0442\u043a\u0438 \u0432\u043f\u0435\u0440\u0451\u0434.
        clock.advance(days=1)
        second = await use_case.execute()

        assert first.triggered is True
        assert second.triggered is True
        assert len(audit.entries) == 2
        # \u041a\u043b\u044e\u0447\u0438 \u0440\u0430\u0437\u043d\u044b\u0435 \u043f\u043e \u0434\u0430\u0442\u0435.
        keys = {e.idempotency_key for e in audit.entries}
        assert len(keys) == 2
        assert len(alerter.events) == 2

    @pytest.mark.asyncio
    async def test_max_dau_one_alerts_at_first_active(self) -> None:
        # MAX=1 \u2192 0.8 \u2248 0 \u2192 \u0430\u043b\u0451\u0440\u0442 \u0441\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442 \u0443\u0436\u0435 \u043f\u0440\u0438 \u043f\u0435\u0440\u0432\u043e\u043c \u0438\u0433\u0440\u043e\u043a\u0435.
        use_case, _uow, audit, _idem, alerter, _c, _l, _ = _build(initial_dau=1, max_dau=1)

        result = await use_case.execute()

        assert result.triggered is True
        assert result.current_dau == 1
        assert result.percent == 100
        assert len(audit.entries) == 1
        assert len(alerter.events) == 1

    @pytest.mark.asyncio
    async def test_pre_seeded_idempotency_skips_alert(self) -> None:
        use_case, uow, audit, idem, alerter, _c, _l, clock = _build(initial_dau=8, max_dau=10)
        # \u0410\u043b\u0451\u0440\u0442 \u0437\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f \u0443\u0436\u0435 \u0431\u044b\u043b (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440, \u043f\u043e\u0441\u043b\u0435 \u0440\u0435\u0441\u0442\u0430\u0440\u0442\u0430).
        key = idem.build(
            DAU_THRESHOLD_NAMESPACE,
            [clock.moscow_date().isoformat()],
        )
        await idem.mark(key, namespace=DAU_THRESHOLD_NAMESPACE)

        result = await use_case.execute()

        assert result.triggered is False
        assert audit.entries == []
        assert alerter.events == []
        # UoW \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u043b\u0441\u044f \u043d\u0430 is_seen, \u043d\u043e \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043f\u0438\u0441\u0430\u043b.
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_max_dau_overshoot_still_triggers_once(self) -> None:
        # current=15, max=10 (\u043b\u0438\u043c\u0438\u0442 \u0443\u043c\u0435\u043d\u044c\u0448\u0438\u043b\u0438 \u0432\u043d\u0438\u0437) \u2014 \u0430\u043b\u0451\u0440\u0442 \u043f\u043e \u043f\u043e\u0440\u043e\u0433\u0443.
        use_case, _uow, audit, _idem, alerter, _c, _l, _ = _build(initial_dau=15, max_dau=10)

        result = await use_case.execute()

        assert result.triggered is True
        assert result.current_dau == 15
        assert result.max_dau == 10
        assert (
            result.percent == 150
        )  # \u043f\u0435\u0440\u0435\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 \u043e\u0442\u0440\u0430\u0436\u0430\u0435\u0442\u0441\u044f \u0432 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0435
        # \u0410\u0443\u0434\u0438\u0442 \u043f\u0438\u0448\u0435\u0442 \u0444\u0438\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u043f\u043e\u0440\u043e\u0433 80%, \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u0432 alerter.events.
        assert audit.entries[0].after == {
            "current_dau": 15,
            "max_dau": 10,
            "percent": DAU_THRESHOLD_PERCENT,
        }
        assert alerter.events[0].current_dau == 15
        assert alerter.events[0].percent == DAU_THRESHOLD_PERCENT


class TestCheckDauThresholdResult:
    def test_percent_zero_max_dau_returns_zero(self) -> None:
        # Edge case: MAX=0 (теоретически невозможен, но проверяем устойчивость).
        result = CheckDauThresholdResult(triggered=False, current_dau=0, max_dau=0)
        assert result.percent == 0
