"""Smoke-тесты port-интерфейсов `domain/bosses/repositories.py` (Спринт 3.3-A).

Реализации портов появятся в Спринте 3.3-B (SQLAlchemy + миграция
`0020_boss_fights`). Здесь убеждаемся только, что ABC-методы объявлены
как `@abstractmethod` и неконкретный класс нельзя инстанцировать.
"""

from __future__ import annotations

import inspect

import pytest

from pipirik_wars.domain.bosses.repositories import (
    IBossFightRepository,
    IBossParticipantRepository,
)


class TestIBossFightRepository:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            IBossFightRepository()  # type: ignore[abstract]

    def test_required_methods_are_abstract(self) -> None:
        expected = {
            "add",
            "get_by_id",
            "get_active_for_player",
            "get_last_global_started_at",
            "save",
        }
        actual = IBossFightRepository.__abstractmethods__
        assert expected == set(actual)

    def test_methods_are_async(self) -> None:
        for name in (
            "add",
            "get_by_id",
            "get_active_for_player",
            "get_last_global_started_at",
            "save",
        ):
            method = getattr(IBossFightRepository, name)
            assert inspect.iscoroutinefunction(method), name


class TestIBossParticipantRepository:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            IBossParticipantRepository()  # type: ignore[abstract]

    def test_required_methods_are_abstract(self) -> None:
        expected = {
            "add",
            "list_by_boss_fight",
            "get_by_boss_fight_and_player",
            "remove",
        }
        actual = IBossParticipantRepository.__abstractmethods__
        assert expected == set(actual)

    def test_methods_are_async(self) -> None:
        for name in (
            "add",
            "list_by_boss_fight",
            "get_by_boss_fight_and_player",
            "remove",
        ):
            method = getattr(IBossParticipantRepository, name)
            assert inspect.iscoroutinefunction(method), name
