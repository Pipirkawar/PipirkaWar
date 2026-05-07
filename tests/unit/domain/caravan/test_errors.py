"""Тесты доменных ошибок `domain/caravan/errors.py` (Спринт 3.2-A)."""

from __future__ import annotations

from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    CaravanCapacityExceededError,
    CaravanCooldownError,
    CaravanError,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanRequirementError,
    CaravanRoleConflictError,
)
from pipirik_wars.shared.errors import DomainError


class TestErrorHierarchy:
    def test_caravan_error_is_domain_error(self) -> None:
        err = CaravanError("base")
        assert isinstance(err, DomainError)

    def test_all_subclasses_inherit_from_caravan_error(self) -> None:
        for cls in (
            AlreadyInCaravanError,
            CaravanCapacityExceededError,
            CaravanCooldownError,
            CaravanLobbyClosedError,
            CaravanNotFoundError,
            CaravanRequirementError,
            CaravanRoleConflictError,
        ):
            assert issubclass(cls, CaravanError)


class TestErrorPayloads:
    def test_caravan_not_found_carries_id(self) -> None:
        err = CaravanNotFoundError(caravan_id=42)
        assert err.caravan_id == 42
        assert "42" in str(err)

    def test_already_in_caravan_carries_player(self) -> None:
        err = AlreadyInCaravanError(player_id=99)
        assert err.player_id == 99
        assert "99" in str(err)

    def test_cooldown_carries_remaining_seconds(self) -> None:
        err = CaravanCooldownError(clan_id=10, actual_remaining_seconds=3600)
        assert err.clan_id == 10
        assert err.actual_remaining_seconds == 3600
        assert "10" in str(err)
        assert "3600" in str(err)

    def test_role_conflict_carries_attempted_role_and_reason(self) -> None:
        err = CaravanRoleConflictError(
            player_id=42,
            attempted_role="raider",
            reason="member of sender clan",
        )
        assert err.player_id == 42
        assert err.attempted_role == "raider"
        assert err.reason == "member of sender clan"
        assert "raider" in str(err)
        assert "member of sender clan" in str(err)

    def test_requirement_carries_all_fields(self) -> None:
        err = CaravanRequirementError(player_id=42, requirement="thickness", required=7, actual=5)
        assert err.player_id == 42
        assert err.requirement == "thickness"
        assert err.required == 7
        assert err.actual == 5
        assert "thickness" in str(err)
        assert "7" in str(err)
        assert "5" in str(err)

    def test_lobby_closed_carries_status(self) -> None:
        err = CaravanLobbyClosedError(caravan_id=1, status="in_battle")
        assert err.caravan_id == 1
        assert err.status == "in_battle"
        assert "in_battle" in str(err)

    def test_capacity_exceeded_carries_role_and_limit(self) -> None:
        err = CaravanCapacityExceededError(caravan_id=1, role="raider", limit=12)
        assert err.caravan_id == 1
        assert err.role == "raider"
        assert err.limit == 12
        assert "raider" in str(err)
        assert "12" in str(err)
