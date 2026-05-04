"""Тесты `StructlogDauThresholdAlerter` (Спринт 1.2.D)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import structlog

from pipirik_wars.infrastructure.dau import StructlogDauThresholdAlerter


@pytest.mark.asyncio
async def test_emit_writes_warning_with_structured_fields() -> None:
    """`emit(...)` пишет structlog-warning со всеми полями."""
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[cap])
    alerter = StructlogDauThresholdAlerter(logger=structlog.get_logger("test_dau_threshold"))
    moment = datetime(2026, 5, 4, 12, 30, tzinfo=UTC)

    await alerter.emit(
        current_dau=8,
        max_dau=10,
        percent=80,
        occurred_at=moment,
    )

    assert len(cap.entries) == 1
    record = cap.entries[0]
    assert record["log_level"] == "warning"
    assert record["event"] == "dau.threshold.reached"
    assert record["current_dau"] == 8
    assert record["max_dau"] == 10
    assert record["percent"] == 80
    assert record["occurred_at"] == moment.isoformat()


@pytest.mark.asyncio
async def test_emit_uses_default_logger_when_none_passed() -> None:
    """Без явного logger-а адаптер использует `structlog.get_logger(...)`."""
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[cap])
    alerter = StructlogDauThresholdAlerter()

    await alerter.emit(
        current_dau=4,
        max_dau=5,
        percent=80,
        occurred_at=datetime(2026, 5, 4, tzinfo=UTC),
    )

    assert len(cap.entries) == 1
    assert cap.entries[0]["event"] == "dau.threshold.reached"
