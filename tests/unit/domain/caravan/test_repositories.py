"""Smoke-тесты port-интерфейсов `domain/caravan/repositories.py` (Спринт 3.2-A).

Реализации портов появятся в Спринте 3.2-B (SQLAlchemy + миграция
`0019_caravans`). Здесь убеждаемся только, что ABC-методы объявлены
как `@abstractmethod` и неконкретный класс нельзя инстанцировать.
"""

from __future__ import annotations

import inspect

import pytest

from pipirik_wars.domain.caravan.repositories import (
    ICaravanParticipantRepository,
    ICaravanRepository,
)


class TestICaravanRepository:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            ICaravanRepository()  # type: ignore[abstract]

    def test_required_methods_are_abstract(self) -> None:
        expected = {
            "add",
            "get_by_id",
            "get_active_by_clan",
            "get_last_finished_at_for_clan",
            "save",
        }
        actual = ICaravanRepository.__abstractmethods__
        assert expected == set(actual)

    def test_methods_are_async(self) -> None:
        for name in (
            "add",
            "get_by_id",
            "get_active_by_clan",
            "get_last_finished_at_for_clan",
            "save",
        ):
            method = getattr(ICaravanRepository, name)
            assert inspect.iscoroutinefunction(method), name


class TestICaravanParticipantRepository:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            ICaravanParticipantRepository()  # type: ignore[abstract]

    def test_required_methods_are_abstract(self) -> None:
        expected = {"add", "list_by_caravan", "list_by_caravan_and_role", "remove"}
        actual = ICaravanParticipantRepository.__abstractmethods__
        assert expected == set(actual)

    def test_methods_are_async(self) -> None:
        for name in ("add", "list_by_caravan", "list_by_caravan_and_role", "remove"):
            method = getattr(ICaravanParticipantRepository, name)
            assert inspect.iscoroutinefunction(method), name
