"""Юнит-тесты `application.i18n.locale` (Спринт 1.5.A / ПД 1.5.2)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Locale,
    LocaleResolver,
)


class TestLocale:
    @pytest.mark.parametrize("code", ["ru", "en"])
    def test_constructs_for_supported_codes(self, code: str) -> None:
        locale = Locale(code)
        assert locale.code == code

    @pytest.mark.parametrize("code", ["fr", "RU", "de", "", "ru-RU", " ru"])
    def test_rejects_unsupported_codes(self, code: str) -> None:
        with pytest.raises(ValueError, match="unsupported locale"):
            Locale(code)

    def test_value_object_equality(self) -> None:
        assert Locale("ru") == Locale("ru")
        assert Locale("ru") != Locale("en")
        assert hash(Locale("ru")) == hash(Locale("ru"))

    def test_default_is_english(self) -> None:
        assert Locale("en") == DEFAULT_LOCALE

    def test_supported_locales_is_immutable(self) -> None:
        assert isinstance(SUPPORTED_LOCALES, frozenset)
        assert {"ru", "en"} == SUPPORTED_LOCALES


class TestLocaleResolver:
    def setup_method(self) -> None:
        self.resolver = LocaleResolver()

    @pytest.mark.parametrize(
        ("tg_lang", "expected"),
        [
            ("ru", Locale("ru")),
            ("ru-RU", Locale("ru")),
            ("RU", Locale("ru")),
            ("ru_RU", Locale("ru")),
            ("RU-ru", Locale("ru")),
        ],
    )
    def test_resolves_russian_variants(self, tg_lang: str, expected: Locale) -> None:
        assert self.resolver.resolve(tg_lang=tg_lang) == expected

    @pytest.mark.parametrize(
        ("tg_lang", "expected"),
        [
            ("en", Locale("en")),
            ("en-US", Locale("en")),
            ("en-GB", Locale("en")),
            ("EN", Locale("en")),
        ],
    )
    def test_resolves_english_variants(self, tg_lang: str, expected: Locale) -> None:
        assert self.resolver.resolve(tg_lang=tg_lang) == expected

    @pytest.mark.parametrize("tg_lang", [None, "", "  ", "fr", "de", "pt-BR", "zh-CN"])
    def test_unknown_falls_back_to_default(self, tg_lang: str | None) -> None:
        assert self.resolver.resolve(tg_lang=tg_lang) == DEFAULT_LOCALE

    def test_default_can_be_overridden(self) -> None:
        resolver = LocaleResolver(default=Locale("ru"))
        assert resolver.resolve(tg_lang="fr") == Locale("ru")
        assert resolver.resolve(tg_lang=None) == Locale("ru")
        # Известная локаль всё равно резолвится явно:
        assert resolver.resolve(tg_lang="en") == Locale("en")
