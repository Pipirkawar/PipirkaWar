"""Unit-тесты `AnticheatGuard` (Спринт 1.6.E, ГДД §3.3.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.anticheat import AnticheatGuard
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.progression.errors import AnticheatSoftBanError

_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


def _make_player(*, ban_until: datetime | None) -> Player:
    return Player(
        id=1,
        tg_id=42,
        username=Username(value="alice"),
        length=Length(cm=100),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
        anticheat_ban_until=ban_until,
    )


class TestAnticheatGuard:
    def test_no_ban_passes(self) -> None:
        """`anticheat_ban_until is None` → ничего не делает."""
        player = _make_player(ban_until=None)
        # Не должно бросать.
        AnticheatGuard.require_unlocked(player, now=_NOW)

    def test_expired_ban_passes(self) -> None:
        """Истёкший бан (ban_until < now) → ничего не делает."""
        expired = _NOW - timedelta(days=1)
        player = _make_player(ban_until=expired)
        AnticheatGuard.require_unlocked(player, now=_NOW)

    def test_active_ban_raises(self) -> None:
        """Активный бан → `AnticheatSoftBanError` с правильными полями."""
        ban_until = _NOW + timedelta(days=14)
        player = _make_player(ban_until=ban_until)
        with pytest.raises(AnticheatSoftBanError) as exc_info:
            AnticheatGuard.require_unlocked(player, now=_NOW)
        assert exc_info.value.tg_id == 42
        assert exc_info.value.banned_until == ban_until

    def test_boundary_ban_until_equals_now_passes(self) -> None:
        """`now == ban_until` → не бан (см. `is_anticheat_banned`: `now < ban_until`)."""
        ban_until = _NOW
        player = _make_player(ban_until=ban_until)
        # На границе бан уже истёк — гейт пускает.
        AnticheatGuard.require_unlocked(player, now=_NOW)

    def test_active_ban_one_microsecond_in_future_raises(self) -> None:
        """Граница: `now + 1 микросекунда` → ещё в бане."""
        ban_until = _NOW + timedelta(microseconds=1)
        player = _make_player(ban_until=ban_until)
        with pytest.raises(AnticheatSoftBanError):
            AnticheatGuard.require_unlocked(player, now=_NOW)

    def test_static_method_no_constructor_needed(self) -> None:
        """Сервис чистый, без состояния, вызывается через класс."""
        player = _make_player(ban_until=None)
        # Достаточно `AnticheatGuard.require_unlocked(...)` без `AnticheatGuard()`.
        AnticheatGuard.require_unlocked(player, now=_NOW)
