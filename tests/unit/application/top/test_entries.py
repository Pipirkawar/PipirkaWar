"""Юнит-тесты `TopPlayerEntry` (Спринт 1.4.C / ПД 1.4.6)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.domain.player import DisplayName, PlayerName, Title


class TestTopPlayerEntry:
    def test_minimal_fields(self) -> None:
        e = TopPlayerEntry(
            title=None,
            display_name=DisplayName(value="Пипирик"),
            name=None,
            length_cm=2,
        )
        assert e.title is None
        assert e.display_name.value == "Пипирик"
        assert e.name is None
        assert e.length_cm == 2

    def test_full_fields(self) -> None:
        e = TopPlayerEntry(
            title=Title.NEWBIE,
            display_name=DisplayName(value="Хвостик"),
            name=PlayerName(value="Иванушка"),
            length_cm=42,
        )
        assert e.title is Title.NEWBIE
        assert e.name is not None and e.name.value == "Иванушка"

    def test_negative_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="length_cm"):
            TopPlayerEntry(
                title=None,
                display_name=DisplayName(value="x"),
                name=None,
                length_cm=-1,
            )

    def test_frozen(self) -> None:
        e = TopPlayerEntry(
            title=None,
            display_name=DisplayName(value="x"),
            name=None,
            length_cm=10,
        )
        with pytest.raises(FrozenInstanceError):
            e.__setattr__("length_cm", 99)
