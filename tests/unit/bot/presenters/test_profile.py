"""Юнит-тесты `bot/presenters/profile.py` (Спринт 1.1.E → 1.5.C, ГДД §2.1/§2.2).

Покрываем:

1. `render_full_nick` (legacy, ещё используется forest-презентером) —
   все 4 сочетания «есть/нет титула × есть/нет имени» плюс новые-локализованные
   титулы (`NEWBIE`).
2. `ProfilePresenter`:
   * `group()` / `other()` / `not_registered()` дают строки из `.ftl`,
     отличные между RU и EN (т.е. локализация реально работает);
   * `card()` — целостный рендер карточки: длина/толщина/секция «Экипировка»
     присутствуют; локализованный титул (`profile-title-newbie`) лежит на
     первой строке (вместо hardcoded RU «Новичок»);
   * `card()` для нового игрока без титула/имени → первая строка только
     `🏷 <display_name>` (Acceptance ГДД §2.2).
3. `title_message_key(Title.X) == MessageKey("profile-title-x")` —
   контракт между презентером и `.ftl`. Если в `Title` появится новый
   член без соответствующего ключа в `.ftl`, `IMessageBundle.format`
   бросит `MessageKeyError` и тесты падут — это намеренный «безопасник».
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.player import ProfileView
from pipirik_wars.bot.presenters.profile import (
    ProfilePresenter,
    render_full_nick,
    title_message_key,
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
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


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


def _fluent_bundle() -> IMessageBundle:
    """Реальный FluentMessageBundle поверх locales/{ru,en}.ftl.

    Используется для интеграционных проверок «карточка действительно
    рендерится с правильной длиной/толщиной/секциями». Маркерный
    `FakeMessageBundle` использован для проверки конкретных ключей.
    """
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


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


class TestTitleMessageKey:
    def test_newbie_maps_to_profile_title_newbie(self) -> None:
        assert title_message_key(Title.NEWBIE) == MessageKey("profile-title-newbie")

    def test_every_title_value_resolves_in_real_bundle(self) -> None:
        """Каждое значение `Title` → соответствующий ключ в `.ftl`.

        Если в `Title` добавят новый член без ключа `profile-title-<value>`,
        `FluentMessageBundle.format` бросит `MessageKeyError` и этот тест
        упадёт. Это и есть напоминание перевести.
        """
        bundle = _fluent_bundle()
        for member in Title:
            for locale in (Locale("ru"), Locale("en")):
                rendered = bundle.format(title_message_key(member), locale=locale)
                assert rendered, f"empty title for {member} / {locale.code}"


class TestProfilePresenterChatBranches:
    """Проверяем, что презентер прогоняет ровно те ключи, которые
    обещаны в контракте, через `IMessageBundle`."""

    def _make(self) -> ProfilePresenter:
        return ProfilePresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_group_uses_profile_group_key(self) -> None:
        assert self._make().group(locale=Locale("ru")) == "ru:profile-group"

    def test_other_uses_profile_other_key(self) -> None:
        assert self._make().other(locale=Locale("en")) == "en:profile-other"

    def test_not_registered_uses_profile_not_registered_key(self) -> None:
        assert self._make().not_registered(locale=Locale("ru")) == "ru:profile-not-registered"


class TestProfilePresenterCard:
    """Интеграционный рендер `card()` через реальный `FluentMessageBundle`."""

    def test_card_includes_length_thickness_and_equipment_stub_ru(self) -> None:
        presenter = ProfilePresenter(bundle=_fluent_bundle())
        view = ProfileView(
            player=_build_player(
                title=Title.NEWBIE,
                name=PlayerName(value="Коляндр"),
            ),
            display_name=DisplayName(value="Бананчик"),
        )
        card = presenter.card(view, locale=Locale("ru"))
        assert "Новичок Бананчик Коляндр" in card
        assert "47 см" in card
        assert "Толщина: 5" in card
        assert "Экипировка" in card

    def test_card_for_fresh_player_just_shows_display_name_ru(self) -> None:
        # Acceptance ГДД §2.2: новичок без титула/имени → «Пипирик».
        presenter = ProfilePresenter(bundle=_fluent_bundle())
        view = ProfileView(
            player=_build_player(
                title=None,
                name=None,
                length_cm=2,
                thickness_level=1,
            ),
            display_name=DisplayName(value="Пипирик"),
        )
        card = presenter.card(view, locale=Locale("ru"))
        first_line = card.splitlines()[0]
        assert first_line == "🏷 Пипирик"
        assert "2 см" in card
        assert "Толщина: 1" in card

    def test_card_layout_matches_gdd_section_2_2_skeleton(self) -> None:
        # 6 не-пустых строк в фиксированном порядке (плюс пустые-разделители).
        presenter = ProfilePresenter(bundle=_fluent_bundle())
        view = ProfileView(
            player=_build_player(
                title=Title.NEWBIE,
                name=PlayerName(value="Иванушка"),
            ),
            display_name=DisplayName(value="Бананчик"),
        )
        card = presenter.card(view, locale=Locale("ru"))
        lines = card.splitlines()
        assert lines[0].startswith("🏷 ")
        assert lines[1] == ""
        assert lines[2].startswith("📏")
        assert lines[3].startswith("📐")
        assert lines[4] == ""
        assert lines[5].startswith("🎽")

    def test_card_renders_in_english_with_localized_title_and_labels(self) -> None:
        # Cross-locale: те же поля, но «Новичок» → «Newbie», «Длина:» → «Length:» и т.д.
        presenter = ProfilePresenter(bundle=_fluent_bundle())
        view = ProfileView(
            player=_build_player(
                title=Title.NEWBIE,
                name=PlayerName(value="Coliander"),
            ),
            display_name=DisplayName(value="Banana"),
        )
        card = presenter.card(view, locale=Locale("en"))
        assert "Newbie Banana Coliander" in card
        assert "47 cm" in card
        assert "Thickness: 5" in card
        assert "Equipment" in card
        # Ни одной русской буквы (грубая, но эффективная проверка).
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in card)
