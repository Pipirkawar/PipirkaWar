"""Юнит-тесты `ClanTopPresenter` (Спринт 2.2.A / ПД 2.2.1).

Покрываем:
1. Пустой топ → один ключ `clantop-empty`, ни одного `clantop-entry`.
2. Заголовок (`clantop-header`) лежит первой строкой, потом пустая,
   потом ряды (`clantop-entry` × N).
3. Корректные параметры в `clantop-entry`: `rank`, `clan_title`,
   `total_length_cm`, `member_count`.
4. Порядок entries сохраняется (1, 2, 3 …).
5. Полный «end-to-end» рендер через настоящий `FluentMessageBundle`
   (RU и EN) — гарантирует, что ключи `.ftl` действительно есть.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.top import ClanTopEntry
from pipirik_wars.bot.presenters.clantop import ClanTopPresenter
from pipirik_wars.domain.clan import ClanTitle
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _entry(
    *,
    clan_id: int = 1,
    title: str = "Львы",
    total: int = 100,
    members: int = 3,
) -> ClanTopEntry:
    return ClanTopEntry(
        clan_id=clan_id,
        clan_title=ClanTitle(title),
        total_length_cm=total,
        member_count=members,
    )


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


class TestClanTopPresenterFakeBundle:
    """Маркерный bundle: проверяем, какие ключи зовёт презентер."""

    def _make(self) -> ClanTopPresenter:
        return ClanTopPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_empty_uses_clantop_empty_key(self) -> None:
        text = self._make().render([], locale=Locale("ru"))
        assert text == "ru:clantop-empty"

    def test_non_empty_uses_header_then_entries(self) -> None:
        text = self._make().render(
            [_entry(total=42, members=5, title="Soldiers")],
            locale=Locale("en"),
        )
        lines = text.split("\n")
        assert lines[0] == "en:clantop-header"
        assert lines[1] == ""
        # FakeMessageBundle сериализует параметры детерминированно.
        assert "en:clantop-entry[" in lines[2]
        assert "rank=1" in lines[2]
        assert "total_length_cm=42" in lines[2]
        assert "member_count=5" in lines[2]
        assert "clan_title=Soldiers" in lines[2]

    def test_preserves_order_of_entries(self) -> None:
        entries = [
            _entry(clan_id=10, total=300, title="A"),
            _entry(clan_id=20, total=200, title="B"),
            _entry(clan_id=30, total=100, title="C"),
        ]
        text = self._make().render(entries, locale=Locale("ru"))
        # rank=1 → A, rank=2 → B, rank=3 → C, в этом порядке.
        a = text.index("rank=1")
        b = text.index("rank=2")
        c = text.index("rank=3")
        assert a < b < c
        a_title = text.index("clan_title=A")
        b_title = text.index("clan_title=B")
        c_title = text.index("clan_title=C")
        assert a_title < b_title < c_title


class TestClanTopPresenterFluent:
    """End-to-end через реальный `.ftl`: ловим отсутствие ключей."""

    def _make(self) -> ClanTopPresenter:
        return ClanTopPresenter(bundle=_fluent_bundle())

    def test_ru_empty_returns_localized_string(self) -> None:
        text = self._make().render([], locale=Locale("ru"))
        assert "Кланов" in text or "клан" in text.lower()

    def test_en_empty_returns_localized_string(self) -> None:
        text = self._make().render([], locale=Locale("en"))
        # «No clans …» — fallback-чек на наличие английского слова.
        assert "clan" in text.lower()

    def test_ru_entry_renders_total_and_members(self) -> None:
        text = self._make().render(
            [_entry(clan_id=1, total=420, members=7, title="Львы")], locale=Locale("ru")
        )
        assert "Львы" in text
        assert "420" in text
        assert "7" in text

    def test_en_entry_renders_total_and_members(self) -> None:
        text = self._make().render(
            [_entry(clan_id=1, total=99, members=2, title="Soldiers")], locale=Locale("en")
        )
        assert "Soldiers" in text
        assert "99" in text
        assert "2" in text
