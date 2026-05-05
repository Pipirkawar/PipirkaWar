"""Юнит-тесты `AnticheatWindow` (Спринт 1.6.C / ГДД §3.3)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.anticheat import AnticheatWindow

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)


class TestConstruction:
    def test_valid(self) -> None:
        w = AnticheatWindow(
            player_id=42,
            since=_NOW - timedelta(days=1),
            organic_sum_cm=100,
        )
        assert w.player_id == 42
        assert w.since == _NOW - timedelta(days=1)
        assert w.organic_sum_cm == 100

    def test_zero_sum_allowed(self) -> None:
        w = AnticheatWindow(
            player_id=1,
            since=_NOW,
            organic_sum_cm=0,
        )
        assert w.organic_sum_cm == 0

    def test_negative_sum_rejected(self) -> None:
        with pytest.raises(ValueError, match="organic_sum_cm must be >= 0"):
            AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=-1)

    def test_zero_player_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="player_id must be > 0"):
            AnticheatWindow(player_id=0, since=_NOW, organic_sum_cm=0)

    def test_negative_player_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="player_id must be > 0"):
            AnticheatWindow(player_id=-5, since=_NOW, organic_sum_cm=0)

    def test_naive_since_rejected(self) -> None:
        naive = datetime(2026, 5, 5, 12, 0, 0)
        with pytest.raises(ValueError, match="must be timezone-aware"):
            AnticheatWindow(player_id=1, since=naive, organic_sum_cm=0)

    def test_frozen(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=10)
        with pytest.raises(FrozenInstanceError):
            w.organic_sum_cm = 999


class TestRemainingCap:
    def test_under_cap(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=1000)
        assert w.remaining_cap_cm(cap_cm=3000) == 2000

    def test_at_cap_returns_zero(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=3000)
        assert w.remaining_cap_cm(cap_cm=3000) == 0

    def test_over_cap_returns_zero(self) -> None:
        # При обходе clamp-а сумма может превысить cap; remaining клеймится в 0.
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=5000)
        assert w.remaining_cap_cm(cap_cm=3000) == 0

    def test_zero_sum(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=0)
        assert w.remaining_cap_cm(cap_cm=3000) == 3000

    def test_negative_cap_rejected(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=10)
        with pytest.raises(ValueError, match="cap_cm must be >= 0"):
            w.remaining_cap_cm(cap_cm=-1)


class TestIsExceeded:
    def test_under_cap(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=2999)
        assert w.is_exceeded(cap_cm=3000) is False

    def test_at_cap_not_exceeded(self) -> None:
        # Строго `>`: ровно cap — это «впритык», не trip-wire.
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=3000)
        assert w.is_exceeded(cap_cm=3000) is False

    def test_above_cap_exceeded(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=3001)
        assert w.is_exceeded(cap_cm=3000) is True

    def test_zero_sum_zero_cap(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=0)
        assert w.is_exceeded(cap_cm=0) is False

    def test_negative_cap_rejected(self) -> None:
        w = AnticheatWindow(player_id=1, since=_NOW, organic_sum_cm=10)
        with pytest.raises(ValueError, match="cap_cm must be >= 0"):
            w.is_exceeded(cap_cm=-1)
