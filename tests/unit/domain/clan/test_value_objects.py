"""Тесты на VO домена «Клан» (Спринт 1.1)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.clan.value_objects import ChatKind, ClanStatus, ClanTitle


class TestChatKind:
    def test_values_match_telegram(self) -> None:
        assert ChatKind.GROUP.value == "group"
        assert ChatKind.SUPERGROUP.value == "supergroup"

    def test_str_compatibility(self) -> None:
        assert ChatKind.GROUP.value == "group"
        assert isinstance(ChatKind.GROUP, str)


class TestClanStatus:
    def test_values_are_stable(self) -> None:
        assert ClanStatus.ACTIVE.value == "active"
        assert ClanStatus.FROZEN.value == "frozen"


class TestClanTitle:
    def test_simple_title_is_allowed(self) -> None:
        ClanTitle(value="Лесные братья")

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ClanTitle(value="")

    def test_whitespace_only_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ClanTitle(value="   ")

    def test_leading_trailing_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="leading/trailing whitespace"):
            ClanTitle(value=" Группа")
        with pytest.raises(ValueError, match="leading/trailing whitespace"):
            ClanTitle(value="Группа ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="length must be <="):
            ClanTitle(value="X" * 256)

    def test_at_limit_is_allowed(self) -> None:
        ClanTitle(value="X" * 255)

    def test_equality(self) -> None:
        assert ClanTitle(value="A") == ClanTitle(value="A")
        assert ClanTitle(value="A") != ClanTitle(value="B")
