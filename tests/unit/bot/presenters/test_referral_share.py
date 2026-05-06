"""Unit-тесты для `ReferralSharePresenter` (Спринт 2.4.D-b, ГДД §13.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.referral_share import (
    ReferralSharePresenter,
    ShareKind,
    parse_referral_share_callback_data,
    referral_share_callback_data,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _fake() -> ReferralSharePresenter:
    return ReferralSharePresenter(bundle=FakeMessageBundle())


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(
        locales_dir=Path(__file__).resolve().parents[4] / "locales",
    )


def _fluent() -> ReferralSharePresenter:
    return ReferralSharePresenter(bundle=_fluent_bundle())


# ─────────────── callback_data round-trip ───────────────


class TestReferralShareCallbackData:
    def test_serialize_duel(self) -> None:
        assert referral_share_callback_data(ShareKind.DUEL, 42) == "ref-share:duel:42"

    def test_serialize_forest(self) -> None:
        assert referral_share_callback_data(ShareKind.FOREST, 7) == "ref-share:forest:7"

    def test_serialize_rejects_zero_id(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            referral_share_callback_data(ShareKind.DUEL, 0)

    def test_serialize_rejects_negative_id(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            referral_share_callback_data(ShareKind.FOREST, -1)

    def test_parse_duel(self) -> None:
        parsed = parse_referral_share_callback_data("ref-share:duel:13")
        assert parsed.kind is ShareKind.DUEL
        assert parsed.entity_id == 13

    def test_parse_forest(self) -> None:
        parsed = parse_referral_share_callback_data("ref-share:forest:99")
        assert parsed.kind is ShareKind.FOREST
        assert parsed.entity_id == 99

    def test_parse_rejects_unknown_prefix(self) -> None:
        with pytest.raises(ValueError, match="ref-share"):
            parse_referral_share_callback_data("xxx:duel:1")

    def test_parse_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="unknown share kind"):
            parse_referral_share_callback_data("ref-share:caravan:1")

    def test_parse_rejects_non_int_id(self) -> None:
        with pytest.raises(ValueError, match="entity_id must be int"):
            parse_referral_share_callback_data("ref-share:duel:abc")

    def test_parse_rejects_zero_id(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            parse_referral_share_callback_data("ref-share:duel:0")

    def test_parse_rejects_wrong_part_count(self) -> None:
        with pytest.raises(ValueError, match="invalid"):
            parse_referral_share_callback_data("ref-share:duel:1:extra")

    def test_round_trip_duel(self) -> None:
        data = referral_share_callback_data(ShareKind.DUEL, 17)
        parsed = parse_referral_share_callback_data(data)
        assert parsed.kind is ShareKind.DUEL
        assert parsed.entity_id == 17

    def test_round_trip_forest(self) -> None:
        data = referral_share_callback_data(ShareKind.FOREST, 25)
        parsed = parse_referral_share_callback_data(data)
        assert parsed.kind is ShareKind.FOREST
        assert parsed.entity_id == 25


# ─────────────── presenter — texts (FakeBundle, маркерные ключи) ───────────────


class TestReferralSharePresenterFakeBundle:
    def test_share_text_duel_victory_passes_all_fields(self) -> None:
        text = _fake().share_text_duel_victory(
            winner_name="@alice",
            loser_name="@bob",
            delta_cm=12,
            winner_length_cm=59,
            sharer_tg_id=123,
            locale=Locale("ru"),
        )
        assert "ru:referral-share-duel-victory" in text
        assert "winner=@alice" in text
        assert "loser=@bob" in text
        assert "delta_cm=12" in text
        assert "winner_length_cm=59" in text
        assert "deeplink=t.me/pipirik_bot?start=ref_123" in text

    def test_share_text_duel_draw_passes_all_fields(self) -> None:
        text = _fake().share_text_duel_draw(
            p1_name="@a",
            p2_name="@b",
            sharer_tg_id=42,
            locale=Locale("en"),
        )
        assert "en:referral-share-duel-draw" in text
        assert "p1=@a" in text
        assert "p2=@b" in text
        assert "deeplink=t.me/pipirik_bot?start=ref_42" in text

    def test_share_text_forest_passes_all_fields(self) -> None:
        text = _fake().share_text_forest(
            player_name="@alice",
            delta_cm=7,
            length_cm=42,
            sharer_tg_id=999,
            locale=Locale("ru"),
        )
        assert "ru:referral-share-forest" in text
        assert "player=@alice" in text
        assert "delta_cm=7" in text
        assert "length_cm=42" in text
        assert "deeplink=t.me/pipirik_bot?start=ref_999" in text

    def test_share_keyboard_duel_one_button(self) -> None:
        kbrd = _fake().share_keyboard_duel(duel_id=7, locale=Locale("ru"))
        assert len(kbrd.inline_keyboard) == 1
        row = kbrd.inline_keyboard[0]
        assert len(row) == 1
        button = row[0]
        assert "ru:referral-share-button" in button.text
        assert button.callback_data == "ref-share:duel:7"

    def test_share_keyboard_forest_one_button(self) -> None:
        kbrd = _fake().share_keyboard_forest(run_id=5, locale=Locale("en"))
        row = kbrd.inline_keyboard[0]
        button = row[0]
        assert "en:referral-share-button" in button.text
        assert button.callback_data == "ref-share:forest:5"

    def test_share_button_duel_returns_inline_button(self) -> None:
        button = _fake().share_button_duel(duel_id=11, locale=Locale("ru"))
        assert button.callback_data == "ref-share:duel:11"

    def test_share_button_forest_returns_inline_button(self) -> None:
        button = _fake().share_button_forest(run_id=22, locale=Locale("en"))
        assert button.callback_data == "ref-share:forest:22"


# ─────────────── presenter — texts (FluentBundle, integration с .ftl) ───────────────


class TestReferralSharePresenterFluentBundle:
    def test_duel_victory_ru_renders_required_fields(self) -> None:
        text = _fluent().share_text_duel_victory(
            winner_name="@alice",
            loser_name="@bob",
            delta_cm=12,
            winner_length_cm=59,
            sharer_tg_id=123,
            locale=Locale("ru"),
        )
        assert "@alice" in text
        assert "@bob" in text
        assert "12" in text
        assert "59" in text
        assert "t.me/pipirik_bot?start=ref_123" in text
        assert "ПИПИРИК ВАРС" in text

    def test_duel_victory_en_renders_required_fields(self) -> None:
        text = _fluent().share_text_duel_victory(
            winner_name="@alice",
            loser_name="@bob",
            delta_cm=12,
            winner_length_cm=59,
            sharer_tg_id=123,
            locale=Locale("en"),
        )
        assert "@alice" in text
        assert "@bob" in text
        assert "PIPIRIK WARS" in text
        assert "t.me/pipirik_bot?start=ref_123" in text

    def test_duel_draw_ru_mentions_both(self) -> None:
        text = _fluent().share_text_duel_draw(
            p1_name="@x",
            p2_name="@y",
            sharer_tg_id=555,
            locale=Locale("ru"),
        )
        assert "@x" in text
        assert "@y" in text
        assert "t.me/pipirik_bot?start=ref_555" in text

    def test_forest_ru_renders_player_and_delta(self) -> None:
        text = _fluent().share_text_forest(
            player_name="@coliander",
            delta_cm=7,
            length_cm=42,
            sharer_tg_id=99,
            locale=Locale("ru"),
        )
        assert "@coliander" in text
        assert "7" in text
        assert "42" in text
        assert "t.me/pipirik_bot?start=ref_99" in text
        assert "лес" in text.lower() or "📏" in text

    def test_share_button_label_ru(self) -> None:
        kbrd = _fluent().share_keyboard_duel(duel_id=1, locale=Locale("ru"))
        button = kbrd.inline_keyboard[0][0]
        assert "Поделиться" in button.text

    def test_share_button_label_en(self) -> None:
        kbrd = _fluent().share_keyboard_duel(duel_id=1, locale=Locale("en"))
        button = kbrd.inline_keyboard[0][0]
        assert "Share" in button.text
