"""Тесты domain-ошибок гор (Спринт 3.1-A)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.mountains.errors import (
    AlreadyInMountainsError,
    MountainError,
    MountainRunNotFoundError,
    MountainRunOwnershipError,
    MountainsRequirementError,
)
from pipirik_wars.shared.errors import DomainError


class TestMountainErrorHierarchy:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            AlreadyInMountainsError,
            MountainRunNotFoundError,
            MountainRunOwnershipError,
            MountainsRequirementError,
        ],
    )
    def test_inherits_mountain_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, MountainError)
        assert issubclass(exc_cls, DomainError)


class TestAlreadyInMountainsError:
    def test_carries_player_id(self) -> None:
        err = AlreadyInMountainsError(player_id=42)
        assert err.player_id == 42
        assert "42" in str(err)


class TestMountainRunNotFoundError:
    def test_carries_run_id(self) -> None:
        err = MountainRunNotFoundError(run_id=7)
        assert err.run_id == 7
        assert "7" in str(err)


class TestMountainRunOwnershipError:
    def test_carries_all_ids(self) -> None:
        err = MountainRunOwnershipError(run_id=10, run_player_id=5, actor_player_id=99)
        assert err.run_id == 10
        assert err.run_player_id == 5
        assert err.actor_player_id == 99
        msg = str(err)
        assert "10" in msg
        assert "5" in msg
        assert "99" in msg


class TestMountainsRequirementError:
    def test_thickness_requirement(self) -> None:
        err = MountainsRequirementError(
            player_id=1,
            requirement="thickness",
            required=3,
            actual=1,
        )
        assert err.requirement == "thickness"
        assert err.required == 3
        assert err.actual == 1
        assert "thickness" in str(err)

    def test_length_requirement(self) -> None:
        err = MountainsRequirementError(
            player_id=2,
            requirement="length",
            required=20,
            actual=15,
        )
        assert err.requirement == "length"
        assert err.required == 20
        assert err.actual == 15
