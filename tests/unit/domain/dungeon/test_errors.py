"""Тесты domain-ошибок данжона (Спринт 3.1-A)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.dungeon.errors import (
    AlreadyInDungeonError,
    DungeonError,
    DungeonRequirementError,
    DungeonRunNotFoundError,
    DungeonRunOwnershipError,
)
from pipirik_wars.shared.errors import DomainError


class TestDungeonErrorHierarchy:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            AlreadyInDungeonError,
            DungeonRunNotFoundError,
            DungeonRunOwnershipError,
            DungeonRequirementError,
        ],
    )
    def test_inherits_dungeon_error(self, exc_cls: type[Exception]) -> None:
        assert issubclass(exc_cls, DungeonError)
        assert issubclass(exc_cls, DomainError)


class TestAlreadyInDungeonError:
    def test_carries_player_id(self) -> None:
        err = AlreadyInDungeonError(player_id=42)
        assert err.player_id == 42
        assert "42" in str(err)


class TestDungeonRunNotFoundError:
    def test_carries_run_id(self) -> None:
        err = DungeonRunNotFoundError(run_id=7)
        assert err.run_id == 7
        assert "7" in str(err)


class TestDungeonRunOwnershipError:
    def test_carries_all_ids(self) -> None:
        err = DungeonRunOwnershipError(run_id=10, run_player_id=5, actor_player_id=99)
        assert err.run_id == 10
        assert err.run_player_id == 5
        assert err.actor_player_id == 99
        msg = str(err)
        assert "10" in msg
        assert "5" in msg
        assert "99" in msg


class TestDungeonRequirementError:
    def test_thickness_requirement(self) -> None:
        err = DungeonRequirementError(
            player_id=1,
            requirement="thickness",
            required=6,
            actual=3,
        )
        assert err.requirement == "thickness"
        assert err.required == 6
        assert err.actual == 3
        assert "thickness" in str(err)

    def test_length_requirement(self) -> None:
        err = DungeonRequirementError(
            player_id=2,
            requirement="length",
            required=20,
            actual=15,
        )
        assert err.requirement == "length"
        assert err.required == 20
