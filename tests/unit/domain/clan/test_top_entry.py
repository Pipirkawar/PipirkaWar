"""Юнит-тесты `ClanTopEntry` (Спринт 2.2.A / ПД 2.2.1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.clan import ClanTitle, ClanTopEntry


def _entry(
    *,
    clan_id: int = 1,
    title: str = "Каравасы",
    total: int = 100,
    members: int = 3,
) -> ClanTopEntry:
    return ClanTopEntry(
        clan_id=clan_id,
        clan_title=ClanTitle(title),
        total_length_cm=total,
        member_count=members,
    )


class TestClanTopEntry:
    def test_basic_fields(self) -> None:
        e = _entry()
        assert e.clan_id == 1
        assert e.clan_title == ClanTitle("Каравасы")
        assert e.total_length_cm == 100
        assert e.member_count == 3

    def test_zero_total_length_allowed(self) -> None:
        e = _entry(total=0)
        assert e.total_length_cm == 0

    def test_zero_member_count_allowed(self) -> None:
        # Нулевое значение — теоретически допустимо (ГДД не запрещает;
        # реализация репо отфильтрует «пустые» кланы, VO не должен).
        e = _entry(members=0)
        assert e.member_count == 0

    def test_negative_total_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="total_length_cm must be >= 0"):
            _entry(total=-1)

    def test_negative_member_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="member_count must be >= 0"):
            _entry(members=-1)

    def test_non_positive_clan_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="clan_id must be > 0"):
            _entry(clan_id=0)
        with pytest.raises(ValueError, match="clan_id must be > 0"):
            _entry(clan_id=-5)

    def test_frozen(self) -> None:
        e = _entry()
        with pytest.raises(FrozenInstanceError):
            e.total_length_cm = 200

    def test_equality_value_semantics(self) -> None:
        e1 = _entry(clan_id=7, title="Алёшки", total=50, members=2)
        e2 = _entry(clan_id=7, title="Алёшки", total=50, members=2)
        e3 = _entry(clan_id=7, title="Алёшки", total=51, members=2)
        assert e1 == e2
        assert e1 != e3
