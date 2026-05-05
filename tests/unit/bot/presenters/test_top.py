"""Юнит-тесты `TopPresenter` (Спринт 1.4.C → 1.5.C, ПД 1.4.6).

Покрываем:

1. Пустой топ → один ключ `top-empty`, ни одного `top-entry`.
2. Заголовок (`top-header`) лежит первой строкой, потом пустая, потом
   ряды (`top-entry` × N).
3. Корректные параметры в `top-entry`: `rank`, `nick`, `length_cm`.
4. Локализация титула берётся из `profile-title-*` (общий ключ с
   `/profile`); для EN → «Newbie», для RU → «Новичок».
5. Все 4 сочетания «есть/нет титула × есть/нет имени».
6. Порядок entries сохраняется (1, 2, 3 …).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.bot.presenters.top import TopPresenter
from pipirik_wars.domain.player import DisplayName, PlayerName, Title
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


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


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


class TestTopPresenterFakeBundle:
    """Маркерный bundle: проверяем, какие ключи зовёт презентер."""

    def _make(self) -> TopPresenter:
        return TopPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_empty_uses_top_empty_key(self) -> None:
        text = self._make().render([], locale=Locale("ru"))
        assert text == "ru:top-empty"

    def test_non_empty_uses_header_then_entries(self) -> None:
        text = self._make().render(
            [_entry(length=42, display_name="Хвостик")],
            locale=Locale("en"),
        )
        lines = text.split("\n")
        assert lines[0] == "en:top-header"
        assert lines[1] == ""
        # FakeMessageBundle сериализует параметры детерминированно
        # — это позволяет тесту проверить именно те значения, что
        # презентер передал в `top-entry`.
        assert "en:top-entry[" in lines[2]
        assert "rank=1" in lines[2]
        assert "length_cm=42" in lines[2]

    def test_passes_localized_title_to_entry_nick(self) -> None:
        text = self._make().render(
            [
                _entry(
                    length=120,
                    title=Title.NEWBIE,
                    display_name="Гигант",
                    name="Иванушка",
                ),
            ],
            locale=Locale("en"),
        )
        # FakeMessageBundle для `profile-title-newbie` вернёт
        # «en:profile-title-newbie» — именно эта строка должна
        # «втечь» в nick через `_render_full_nick`.
        assert "en:profile-title-newbie" in text
        assert "Гигант" in text
        assert "Иванушка" in text


class TestTopPresenterFluent:
    """Интеграционный рендер через настоящий `FluentMessageBundle`."""

    def _presenter(self) -> TopPresenter:
        return TopPresenter(bundle=_fluent_bundle())

    def test_only_display_name_no_title_no_name_ru(self) -> None:
        text = self._presenter().render(
            [_entry(length=42, display_name="Хвостик")],
            locale=Locale("ru"),
        )
        # Без титула/имени строка ровно «1. Хвостик — 42 см».
        assert "1. Хвостик — 42 см" in text

    def test_with_title_and_name_ru(self) -> None:
        text = self._presenter().render(
            [
                _entry(
                    length=120,
                    title=Title.NEWBIE,
                    display_name="Гигант",
                    name="Иванушка",
                ),
            ],
            locale=Locale("ru"),
        )
        assert "1. Новичок Гигант Иванушка — 120 см" in text

    def test_with_title_no_name_ru(self) -> None:
        text = self._presenter().render(
            [_entry(length=10, title=Title.NEWBIE, display_name="Малыш")],
            locale=Locale("ru"),
        )
        assert "1. Новичок Малыш — 10 см" in text

    def test_with_name_no_title_ru(self) -> None:
        text = self._presenter().render(
            [_entry(length=42, display_name="Хвостик", name="Колян")],
            locale=Locale("ru"),
        )
        assert "1. Хвостик Колян — 42 см" in text

    def test_renders_header_and_blank_line_then_entries(self) -> None:
        text = self._presenter().render(
            [
                _entry(length=42, display_name="Хвостик"),
                _entry(length=10, display_name="Малыш"),
            ],
            locale=Locale("ru"),
        )
        lines = text.split("\n")
        assert lines[0] == "🏆 <b>Топ пипириков</b>"
        assert lines[1] == ""
        assert lines[2] == "1. Хвостик — 42 см"
        assert lines[3] == "2. Малыш — 10 см"

    def test_preserves_entries_order(self) -> None:
        entries = [_entry(length=100 - i, display_name=f"D{i}") for i in range(5)]
        text = self._presenter().render(entries, locale=Locale("ru"))
        for i, expected_length in enumerate([100, 99, 98, 97, 96]):
            assert f"{i + 1}. D{i} — {expected_length} см" in text

    def test_empty_uses_friendly_message_ru(self) -> None:
        text = self._presenter().render([], locale=Locale("ru"))
        assert text.startswith("🏆")
        assert "/start" in text

    def test_renders_in_english_with_localized_title(self) -> None:
        text = self._presenter().render(
            [
                _entry(
                    length=120,
                    title=Title.NEWBIE,
                    display_name="Giant",
                    name="John",
                ),
            ],
            locale=Locale("en"),
        )
        assert "1. Newbie Giant John — 120 cm" in text
        # Ни одной русской буквы.
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)
