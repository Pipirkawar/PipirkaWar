"""Unit tests for DashboardStats DTO and helpers (Sprint 4.5-C)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pipirik_wars.application.admin.get_dashboard_stats import (
    DashboardStats,
    ErrorEntry,
    thirty_days_ago_msk,
    today_msk,
)


def _make_error(action: str = "test_action") -> ErrorEntry:
    return ErrorEntry(
        occurred_at=datetime(2026, 5, 13, 12, 0, tzinfo=UTC),
        action=action,
        admin_id=1,
        target_kind="player",
        target_id="42",
        reason="test reason",
    )


def test_dashboard_stats_defaults() -> None:
    stats = DashboardStats(
        dau=10,
        mau=100,
        total_players=500,
        signup_queue_size=3,
        active_caravans=2,
        active_raids=1,
        recent_errors=(),
    )
    assert stats.dau == 10
    assert stats.mau == 100
    assert stats.total_players == 500
    assert stats.signup_queue_size == 3
    assert stats.active_caravans == 2
    assert stats.active_raids == 1
    assert stats.recent_errors == ()


def test_dashboard_stats_with_errors() -> None:
    e1 = _make_error("ban")
    e2 = _make_error("grant")
    stats = DashboardStats(
        dau=0,
        mau=0,
        total_players=0,
        signup_queue_size=0,
        active_caravans=0,
        active_raids=0,
        recent_errors=(e1, e2),
    )
    assert len(stats.recent_errors) == 2
    assert stats.recent_errors[0].action == "ban"
    assert stats.recent_errors[1].action == "grant"


def test_error_entry_fields() -> None:
    now = datetime(2026, 5, 13, 15, 30, tzinfo=UTC)
    entry = ErrorEntry(
        occurred_at=now,
        action="freeze_player",
        admin_id=7,
        target_kind="player",
        target_id="99",
        reason="suspicious activity",
    )
    assert entry.occurred_at == now
    assert entry.action == "freeze_player"
    assert entry.admin_id == 7
    assert entry.target_kind == "player"
    assert entry.target_id == "99"
    assert entry.reason == "suspicious activity"


def test_today_msk_returns_date() -> None:
    result = today_msk()
    assert isinstance(result, date)


def test_thirty_days_ago_msk_returns_date() -> None:
    result = thirty_days_ago_msk()
    assert isinstance(result, date)


def test_thirty_days_ago_is_before_today() -> None:
    today = today_msk()
    ago = thirty_days_ago_msk()
    assert ago < today


def test_thirty_days_gap() -> None:
    today = today_msk()
    ago = thirty_days_ago_msk()
    delta = today - ago
    assert delta == timedelta(days=30)


def test_dashboard_stats_is_frozen() -> None:
    stats = DashboardStats(
        dau=1,
        mau=2,
        total_players=3,
        signup_queue_size=0,
        active_caravans=0,
        active_raids=0,
        recent_errors=(),
    )
    # frozen dataclass
    try:
        stats.dau = 999
    except AttributeError:
        pass
    else:
        raise AssertionError("DashboardStats should be frozen")


def test_error_entry_is_frozen() -> None:
    entry = _make_error()
    try:
        entry.action = "new"
    except AttributeError:
        pass
    else:
        raise AssertionError("ErrorEntry should be frozen")


def test_dashboard_stats_zero_values() -> None:
    stats = DashboardStats(
        dau=0,
        mau=0,
        total_players=0,
        signup_queue_size=0,
        active_caravans=0,
        active_raids=0,
        recent_errors=(),
    )
    assert stats.dau == 0
    assert stats.mau == 0
    assert stats.total_players == 0


def test_dashboard_stats_large_values() -> None:
    stats = DashboardStats(
        dau=100_000,
        mau=1_000_000,
        total_players=5_000_000,
        signup_queue_size=50_000,
        active_caravans=200,
        active_raids=100,
        recent_errors=(),
    )
    assert stats.dau == 100_000
    assert stats.total_players == 5_000_000
