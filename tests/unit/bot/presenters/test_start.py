"""Юнит-тест `StartPresenter` (Спринт 1.5.B).

Проверяет, что презентер прогоняет ровно те ключи и параметры, которые
описаны в контракте, через `IMessageBundle`. Не зависит от Fluent —
использует in-memory `_FakeBundle`.
"""

from __future__ import annotations

from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.start import StartPresenter
from tests.fakes import FakeMessageBundle


def _make() -> StartPresenter:
    return StartPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))


class TestStartPresenter:
    def test_registered_uses_start_registered_key(self) -> None:
        assert _make().registered(locale=Locale("ru")) == "ru:start-registered"

    def test_already_uses_start_already_key(self) -> None:
        assert _make().already(locale=Locale("ru")) == "ru:start-already"

    def test_group_uses_start_group_key(self) -> None:
        assert _make().group(locale=Locale("en")) == "en:start-group"

    def test_other_uses_start_other_key(self) -> None:
        assert _make().other(locale=Locale("en")) == "en:start-other"

    def test_queued_passes_position_param(self) -> None:
        assert _make().queued(locale=Locale("ru"), position=42) == "ru:start-queued[position=42]"

    def test_locale_change_changes_rendered_string(self) -> None:
        presenter = _make()
        assert presenter.registered(locale=Locale("ru")) != presenter.registered(
            locale=Locale("en"),
        )
