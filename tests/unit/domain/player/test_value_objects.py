"""Тесты на VO домена «Игрок» (Спринт 1.1)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.player.value_objects import (
    DisplayName,
    Length,
    PlayerName,
    Thickness,
    Title,
    Username,
)


class TestLength:
    def test_zero_is_allowed(self) -> None:
        Length(cm=0)

    def test_positive_is_allowed(self) -> None:
        Length(cm=2)
        Length(cm=10_000)

    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Length must be >= 0 cm"):
            Length(cm=-1)

    def test_equality_by_value(self) -> None:
        assert Length(cm=2) == Length(cm=2)
        assert Length(cm=2) != Length(cm=3)

    def test_is_frozen(self) -> None:
        length = Length(cm=2)
        with pytest.raises(AttributeError):
            length.cm = 5


class TestThickness:
    def test_one_is_minimum(self) -> None:
        Thickness(level=1)

    def test_positive_is_allowed(self) -> None:
        Thickness(level=5)
        Thickness(level=20)

    def test_zero_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Thickness level must be >= 1"):
            Thickness(level=0)

    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Thickness level must be >= 1"):
            Thickness(level=-1)

    def test_equality_by_value(self) -> None:
        assert Thickness(level=3) == Thickness(level=3)
        assert Thickness(level=3) != Thickness(level=4)


class TestTitle:
    def test_newbie_is_present(self) -> None:
        assert Title.NEWBIE.value == "newbie"

    def test_str_compatibility(self) -> None:
        # Title — `str, enum.Enum`, должна сравниваться по `.value`.
        assert Title.NEWBIE.value == "newbie"
        # И при этом сама принадлежать `str` (для JSON-сериализации).
        assert isinstance(Title.NEWBIE, str)

    def test_unknown_value_does_not_construct(self) -> None:
        with pytest.raises(ValueError):
            Title("__unknown__")


class TestPlayerName:
    def test_simple_name_is_allowed(self) -> None:
        name = PlayerName(value="Иванушка")
        assert name.value == "Иванушка"

    def test_unicode_is_allowed(self) -> None:
        PlayerName(value="Geralt")
        PlayerName(value="Коляндр")
        PlayerName(value="Батонище-3")

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            PlayerName(value="")

    def test_whitespace_only_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            PlayerName(value="   ")

    def test_leading_trailing_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="leading/trailing whitespace"):
            PlayerName(value=" Иван")
        with pytest.raises(ValueError, match="leading/trailing whitespace"):
            PlayerName(value="Иван ")

    def test_too_long_is_rejected(self) -> None:
        # Длина 65 — на 1 больше лимита 64.
        long = "X" * 65
        with pytest.raises(ValueError, match="length must be <="):
            PlayerName(value=long)

    def test_at_limit_is_allowed(self) -> None:
        PlayerName(value="X" * 64)


class TestDisplayName:
    def test_simple_value_is_allowed(self) -> None:
        DisplayName(value="Пипирик")

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            DisplayName(value="")

    def test_whitespace_only_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            DisplayName(value="   \t  ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="length must be <="):
            DisplayName(value="X" * 65)


class TestUsername:
    def test_simple_value_is_allowed(self) -> None:
        Username(value="ivan42")

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Username(value="")

    def test_leading_at_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="leading '@'"):
            Username(value="@ivan42")

    def test_whitespace_padding_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="leading/trailing whitespace"):
            Username(value=" ivan42")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="length must be <="):
            Username(value="X" * 33)

    def test_at_limit_is_allowed(self) -> None:
        Username(value="X" * 32)
