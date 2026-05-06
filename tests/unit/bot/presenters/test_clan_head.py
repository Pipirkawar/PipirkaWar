"""Unit-тесты `ClanHeadPresenter` (Спринт 2.3.E)."""

from __future__ import annotations

from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters import ClanHeadPresenter
from tests.fakes import FakeMessageBundle


def _presenter() -> ClanHeadPresenter:
    return ClanHeadPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))


class TestClanHeadPresenterRendering:
    def test_needs_group_chat_uses_correct_key(self) -> None:
        result = _presenter().needs_group_chat(locale=Locale("ru"))
        assert result == "ru:clan-head-needs-group-chat"

    def test_not_registered_uses_correct_key(self) -> None:
        result = _presenter().not_registered(locale=Locale("en"))
        assert result == "en:clan-head-not-registered"

    def test_frozen_clan_uses_correct_key(self) -> None:
        result = _presenter().frozen_clan(locale=Locale("ru"))
        assert result == "ru:clan-head-frozen-clan"

    def test_not_enough_active_passes_active_and_required(self) -> None:
        result = _presenter().not_enough_active(
            locale=Locale("ru"),
            active_count=2,
            required=5,
        )
        assert result == "ru:clan-head-not-enough-active[active_count=2,required=5]"

    def test_success_passes_all_placeholders(self) -> None:
        result = _presenter().success(
            locale=Locale("ru"),
            head_display_name="Алиса",
            bonus_cm=15,
            new_length_cm=120,
            quote_text="По понятиям, Алиса!",
        )
        assert result == (
            "ru:clan-head-success["
            "bonus_cm=15,"
            "head_display_name=Алиса,"
            "new_length_cm=120,"
            "quote_text=По понятиям, Алиса!]"
        )

    def test_already_assigned_passes_all_placeholders(self) -> None:
        result = _presenter().already_assigned(
            locale=Locale("en"),
            head_display_name="Bob",
            bonus_cm=10,
            quote_text="Statham approves.",
        )
        assert result == (
            "en:clan-head-already-assigned["
            "bonus_cm=10,"
            "head_display_name=Bob,"
            "quote_text=Statham approves.]"
        )
