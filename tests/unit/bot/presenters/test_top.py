"""Юнит-тесты презентера `/top` (Спринт 1.4.C, ПД 1.4.6)."""

from __future__ import annotations

from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.bot.presenters.top import (
    REPLY_TOP_EMPTY_RU,
    REPLY_TOP_HEADER_RU,
    render_top,
    render_top_entry,
)
from pipirik_wars.domain.player import DisplayName, PlayerName, Title


def _entry(
    *,
    length: int,
    title: Title | None = None,
    display_name: str = "Хвостик",
    name: str | None = None,
) -> TopPlayerEntry:
    return TopPlayerEntry(
        title=title,
        display_name=DisplayName(value=display_name),
        name=PlayerName(value=name) if name is not None else None,
        length_cm=length,
    )


class TestRenderTopEntry:
    def test_only_display_name_no_title_no_name(self) -> None:
        line = render_top_entry(_entry(length=42), rank=1)
        assert line == "1. Хвостик — 42 см"

    def test_with_title_and_name(self) -> None:
        line = render_top_entry(
            _entry(
                length=120,
                title=Title.NEWBIE,
                display_name="Гигант",
                name="Иванушка",
            ),
            rank=3,
        )
        assert line == "3. Новичок Гигант Иванушка — 120 см"

    def test_with_title_no_name(self) -> None:
        line = render_top_entry(
            _entry(length=10, title=Title.NEWBIE, display_name="Малыш"),
            rank=99,
        )
        assert line == "99. Новичок Малыш — 10 см"

    def test_with_name_no_title(self) -> None:
        line = render_top_entry(
            _entry(length=42, display_name="Хвостик", name="Колян"),
            rank=2,
        )
        assert line == "2. Хвостик Колян — 42 см"


class TestRenderTop:
    def test_empty_uses_friendly_message(self) -> None:
        assert render_top([]) == REPLY_TOP_EMPTY_RU

    def test_renders_header_and_blank_line_then_entries(self) -> None:
        text = render_top(
            [
                _entry(length=42, display_name="Хвостик"),
                _entry(length=10, display_name="Малыш"),
            ]
        )
        lines = text.split("\n")
        assert lines[0] == REPLY_TOP_HEADER_RU
        assert lines[1] == ""
        assert lines[2] == "1. Хвостик — 42 см"
        assert lines[3] == "2. Малыш — 10 см"

    def test_preserves_entries_order(self) -> None:
        entries = [_entry(length=100 - i, display_name=f"D{i}") for i in range(5)]
        text = render_top(entries)
        for i, expected_length in enumerate([100, 99, 98, 97, 96]):
            assert f"{i + 1}. D{i} — {expected_length} см" in text

    def test_header_starts_with_emoji(self) -> None:
        # Маленький UX-чек: заголовок начинается с эмодзи трофея.
        assert REPLY_TOP_HEADER_RU.startswith("🏆")
        assert REPLY_TOP_EMPTY_RU.startswith("🏆")
