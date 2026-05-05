"""Юнит-тесты `LangPresenter` (Спринт 1.5.F).

Простые проверки: каждый метод дёргает правильный ключ и не теряет
параметры. `confirmed(locale=Locale("ru"))` → ключ `lang-set-ru`,
`confirmed(locale=Locale("en"))` → ключ `lang-set-en`.
"""

from __future__ import annotations

from typing import cast

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

    def test_confirmed_ru_uses_lang_set_ru_key(self) -> None:
        rendered = _presenter().confirmed(locale=Locale("ru"))
        assert rendered == "ru:lang-set-ru"

    def test_confirmed_en_uses_lang_set_en_key(self) -> None:
        rendered = _presenter().confirmed(locale=Locale("en"))
        assert rendered == "en:lang-set-en"
