"""Юнит-тесты `bot/presenters/profile.py` (Спринт 1.1.E, ГДД §2.1/§2.2).

Покрываем:

1. `render_full_nick` — все 4 сочетания «есть/нет титула × есть/нет имени»
   плюс новые-локализованные титулы (`NEWBIE`).
2. `render_profile_card` — целостный рендер карточки, проверяем,
   что в выходной строке есть длина/толщина/секция «Экипировка».
3. Integrity: для несуществующего в `_TITLE_RU` ключа функция падает
   `KeyError` (это и есть «ловим, что забыли локализовать новый Title»).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.player import ProfileView
from pipirik_wars.bot.presenters.profile import (
    render_full_nick,
    render_profile_card,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.domain.player.value_objects import Length


def _build_player(
    *,
    title: Title | None,
    name: PlayerName | None,
    length_cm: int = 47,
    thickness_level: int = 5,
) -> Player:
    return Player(
        id=1,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=title,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )


class TestRenderFullNick:
    def test_no_title_no_name_returns_only_display_name(self) -> None:
        nick = render_full_nick(
            title=None,
            display_name=DisplayName(value="Пипирик"),
            name=None,
        )
        assert nick == "Пипирик"

    def test_with_title_no_name(self) -> None:
        nick = render_full_nick(
            title=Title.NEWBIE,
            display_name=DisplayName(value="Пипирик"),
            name=None,
        )
        assert nick == "Новичок Пипирик"

    def test_no_title_with_name(self) -> None:
        nick = render_full_nick(
            title=None,
            display_name=DisplayName(value="Бананчик"),
            name=PlayerName(value="Иванушка"),
        )
        assert nick == "Бананчик Иванушка"

    def test_with_title_and_name(self) -> None:
        nick = render_full_nick(
            title=Title.NEWBIE,
            display_name=DisplayName(value="Бананчик"),
            name=PlayerName(value="Коляндр"),
        )
        assert nick == "Новичок Бананчик Коляндр"

    def test_only_known_titles_supported(self) -> None:
        # Каждый существующий enum-член должен иметь локализацию.
        # Если в `Title` появится новый член без правки `_TITLE_RU`,
        # этот тест упадёт — это и есть напоминание локализовать.
        for member in Title:
            nick = render_full_nick(
                title=member,
                display_name=DisplayName(value="X"),
                name=None,
            )
            assert nick.endswith("X")
            # Локализованная часть — не пустая и не равна enum-значению
            assert nick.split(" ")[0] != member.value


class TestRenderProfileCard:
    def test_card_includes_length_thickness_and_equipment_stub(self) -> None:
        player = _build_player(
            title=Title.NEWBIE,
            name=PlayerName(value="Коляндр"),
        )
        view = ProfileView(
            player=player,
            display_name=DisplayName(value="Бананчик"),
        )
        card = render_profile_card(view)
        assert "Новичок Бананчик Коляндр" in card
        assert "47 см" in card
        assert "Толщина: 5" in card
        assert "Экипировка" in card  # секция есть, даже если пусто

    def test_card_for_fresh_player_just_shows_display_name(self) -> None:
        # Acceptance ГДД §2.2: новичок без титула/имени → «Пипирик».
        player = _build_player(
            title=None,
            name=None,
            length_cm=2,
            thickness_level=1,
        )
        view = ProfileView(
            player=player,
            display_name=DisplayName(value="Пипирик"),
        )
        card = render_profile_card(view)
        first_line = card.splitlines()[0]
        # Только название, никаких лишних слов.
        assert first_line == "🏷 Пипирик"
        assert "2 см" in card
        assert "Толщина: 1" in card

    def test_card_layout_matches_gdd_section_2_2_skeleton(self) -> None:
        # Структурная проверка: 6 не-пустых строк в фиксированном порядке.
        player = _build_player(
            title=Title.NEWBIE,
            name=PlayerName(value="Иванушка"),
        )
        view = ProfileView(
            player=player,
            display_name=DisplayName(value="Бананчик"),
        )
        card = render_profile_card(view)
        lines = card.splitlines()
        # Скелет: ник / пусто / длина / толщина / пусто / экипировка
        assert lines[0].startswith("🏷 ")
        assert lines[1] == ""
        assert lines[2].startswith("📏")
        assert lines[3].startswith("📐")
        assert lines[4] == ""
        assert lines[5].startswith("🎽")


class TestRenderFullNickInvariants:
    @pytest.mark.parametrize(
        ("title", "name", "expected_words"),
        [
            (None, None, 1),
            (Title.NEWBIE, None, 2),
            (None, PlayerName(value="X"), 2),
            (Title.NEWBIE, PlayerName(value="X"), 3),
        ],
    )
    def test_word_count_matches_present_parts(
        self,
        title: Title | None,
        name: PlayerName | None,
        expected_words: int,
    ) -> None:
        nick = render_full_nick(
            title=title,
            display_name=DisplayName(value="Пипирик"),
            name=name,
        )
        assert len(nick.split(" ")) == expected_words
