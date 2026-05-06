"""Юнит-тесты `ClanQuoteTemplate` (Спринт 2.3.D)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.daily_head import ALLOWED_QUOTE_TAGS, ClanQuoteTemplate


class TestClanQuoteTemplateConstruction:
    def test_minimal_valid_template(self) -> None:
        t = ClanQuoteTemplate(
            id="clan_quote.ru.0001",
            text="Hi {user}",
            tags=("statham",),
        )
        assert t.id == "clan_quote.ru.0001"
        assert t.text == "Hi {user}"
        assert t.tags == ("statham",)

    def test_template_is_frozen(self) -> None:
        t = ClanQuoteTemplate(id="x", text="y", tags=("statham",))
        with pytest.raises((AttributeError, Exception)):
            t.id = "z"

    def test_multiple_style_tags_allowed(self) -> None:
        t = ClanQuoteTemplate(
            id="x",
            text="hi",
            tags=("statham", "vk_pablik"),
        )
        assert "statham" in t.tags
        assert "vk_pablik" in t.tags

    def test_profanity_with_style_tag_allowed(self) -> None:
        t = ClanQuoteTemplate(
            id="x",
            text="hi",
            tags=("vk_pablik", "profanity"),
        )
        assert t.has_profanity is True

    def test_no_profanity_returns_false(self) -> None:
        t = ClanQuoteTemplate(id="x", text="hi", tags=("auf",))
        assert t.has_profanity is False


class TestClanQuoteTemplateValidation:
    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ClanQuoteTemplate(id="", text="hi", tags=("statham",))

    def test_id_with_leading_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ClanQuoteTemplate(id="  x", text="hi", tags=("statham",))

    def test_id_with_trailing_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ClanQuoteTemplate(id="x  ", text="hi", tags=("statham",))

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            ClanQuoteTemplate(id="x", text="", tags=("statham",))

    def test_text_with_leading_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            ClanQuoteTemplate(id="x", text=" hi", tags=("statham",))

    def test_empty_tags_rejected(self) -> None:
        with pytest.raises(ValueError, match="must contain at least one style tag"):
            ClanQuoteTemplate(id="x", text="hi", tags=())

    def test_unknown_tag_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown tags"):
            ClanQuoteTemplate(id="x", text="hi", tags=("statham", "unknown"))

    def test_only_profanity_tag_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one style tag"):
            ClanQuoteTemplate(id="x", text="hi", tags=("profanity",))

    def test_duplicate_tags_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be unique"):
            ClanQuoteTemplate(id="x", text="hi", tags=("statham", "statham"))


class TestAllowedQuoteTags:
    def test_contains_required_style_tags(self) -> None:
        assert "statham" in ALLOWED_QUOTE_TAGS
        assert "vk_pablik" in ALLOWED_QUOTE_TAGS
        assert "auf" in ALLOWED_QUOTE_TAGS
        assert "meme" in ALLOWED_QUOTE_TAGS

    def test_contains_profanity_modifier(self) -> None:
        assert "profanity" in ALLOWED_QUOTE_TAGS

    def test_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_QUOTE_TAGS, frozenset)
