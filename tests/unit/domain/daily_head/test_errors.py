"""Юнит-тесты доменных ошибок «Главы клана дня»."""

from __future__ import annotations

from datetime import date

from pipirik_wars.domain.daily_head import (
    DailyHeadAlreadyAssignedError,
    DailyHeadError,
    DailyHeadInsufficientActivityError,
)
from pipirik_wars.shared.errors import DomainError


class TestDailyHeadInsufficientActivityError:
    def test_inherits_from_daily_head_error(self) -> None:
        err = DailyHeadInsufficientActivityError(clan_id=42, active_count=2, required=5)
        assert isinstance(err, DailyHeadError)
        assert isinstance(err, DomainError)

    def test_payload_fields(self) -> None:
        err = DailyHeadInsufficientActivityError(clan_id=42, active_count=2, required=5)
        assert err.clan_id == 42
        assert err.active_count == 2
        assert err.required == 5

    def test_message_contains_counts(self) -> None:
        err = DailyHeadInsufficientActivityError(clan_id=42, active_count=2, required=5)
        msg = str(err)
        assert "42" in msg
        assert "2" in msg
        assert "5" in msg

    def test_zero_active_count_allowed(self) -> None:
        err = DailyHeadInsufficientActivityError(clan_id=10, active_count=0, required=5)
        assert err.active_count == 0


class TestDailyHeadAlreadyAssignedError:
    def test_inherits_from_daily_head_error(self) -> None:
        err = DailyHeadAlreadyAssignedError(clan_id=42, moscow_date=date(2026, 5, 6))
        assert isinstance(err, DailyHeadError)
        assert isinstance(err, DomainError)

    def test_payload_fields(self) -> None:
        err = DailyHeadAlreadyAssignedError(clan_id=42, moscow_date=date(2026, 5, 6))
        assert err.clan_id == 42
        assert err.moscow_date == date(2026, 5, 6)

    def test_message_contains_clan_and_date(self) -> None:
        err = DailyHeadAlreadyAssignedError(clan_id=42, moscow_date=date(2026, 5, 6))
        msg = str(err)
        assert "42" in msg
        assert "2026-05-06" in msg
