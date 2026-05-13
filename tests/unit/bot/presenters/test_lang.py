"""Юнит-тесты `LangPresenter` (Спринт 1.5.F, расширен в 4.1-K).

Простые проверки: каждый метод дёргает правильный ключ и не теряет
параметры. `confirmed(locale=Locale("<code>"))` → ключ `lang-set-<code>`,
для каждой из 8 поддерживаемых локалей (`SUPPORTED_LOCALES`).
"""

from __future__ import annotations

from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.lang import LangPresenter
from tests.fakes import FakeMessageBundle


def _presenter() -> LangPresenter:
    return LangPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))


class TestLangPresenter:
    def test_group(self) -> None:
        assert _presenter().group(locale=Locale("ru")) == "ru:lang-group"

    def test_other(self) -> None:
        assert _presenter().other(locale=Locale("en")) == "en:lang-other"

    def test_not_registered(self) -> None:
        rendered = _presenter().not_registered(locale=Locale("ru"))
        assert rendered == "ru:lang-not-registered"

    def test_usage(self) -> None:
        assert _presenter().usage(locale=Locale("en")) == "en:lang-usage"

    def test_unsupported_includes_code(self) -> None:
        rendered = _presenter().unsupported(locale=Locale("en"), code="fr")
        assert rendered == "en:lang-unsupported[code=fr]"

    @pytest.mark.parametrize(
        "code",
        ["ru", "en", "pt", "es", "tr", "id", "fa", "uk"],
    )
    def test_confirmed_uses_lang_set_for_each_supported_locale(self, code: str) -> None:
        """4.1-K: для каждой из 8 локалей confirmed() рендерит `lang-set-<code>`."""
        rendered = _presenter().confirmed(locale=Locale(code))
        assert rendered == f"{code}:lang-set-{code}"
