"""Юнит-тесты `ClaimPrizePresenter` + callback-сериализаторов (Спринт 4.1-D.7.a).

`ClaimPrizePresenter` — тонкий слой над `IMessageBundle`, поэтому
тестируем именно склейку ключей и параметров (через
`FakeMessageBundle`-маркеры) и контракт callback-сериализатора
``claim_prize:<lot_id>``.
"""

from __future__ import annotations

from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.claim_prize import (
    ClaimPrizePresenter,
    claim_prize_callback_data,
    parse_claim_prize_callback_data,
)
from tests.fakes import FakeMessageBundle

# ────────────────────────── callback_data ─────────────────────────


class TestClaimPrizeCallbackData:
    def test_small_lot_id_serializes(self) -> None:
        assert claim_prize_callback_data(1) == "claim_prize:1"

    def test_large_lot_id_serializes(self) -> None:
        assert claim_prize_callback_data(987_654_321) == "claim_prize:987654321"

    def test_zero_lot_id_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            claim_prize_callback_data(0)

    def test_negative_lot_id_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            claim_prize_callback_data(-7)

    def test_huge_lot_id_overflows_callback_limit(self) -> None:
        # 64-byte cap: prefix "claim_prize:" is 12 bytes, so lot_id up to
        # 10**52 fits; we craft a string that explicitly exceeds the limit.
        huge_lot_id = 10**60
        with pytest.raises(ValueError, match="exceeds 64 bytes"):
            claim_prize_callback_data(huge_lot_id)

    def test_parse_round_trip(self) -> None:
        parsed = parse_claim_prize_callback_data("claim_prize:42")
        assert parsed.lot_id == 42

    def test_parse_large_lot_id(self) -> None:
        parsed = parse_claim_prize_callback_data("claim_prize:987654321")
        assert parsed.lot_id == 987_654_321

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "claim_prize",
            "claim_prize:",
            "claim_prize:abc",
            "claim_prize:0",
            "claim_prize:-5",
            "claim_prize:1.5",
            "other:42",
            "claim_prize:42:extra",
        ],
    )
    def test_parse_invalid_raises(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_claim_prize_callback_data(raw)


# ────────────────────────── presenter ─────────────────────────────


class TestClaimPrizePresenter:
    def setup_method(self) -> None:
        self.bundle = cast(IMessageBundle, FakeMessageBundle())
        self.presenter = ClaimPrizePresenter(bundle=self.bundle)
        self.ru = Locale("ru")
        self.en = Locale("en")

    # Чат-гарды --------------------------------------------------------

    def test_group(self) -> None:
        assert self.presenter.group(locale=self.ru) == "ru:claim-prize-group"

    def test_other(self) -> None:
        assert self.presenter.other(locale=self.en) == "en:claim-prize-other"

    def test_not_registered(self) -> None:
        assert self.presenter.not_registered(locale=self.ru) == "ru:claim-prize-not-registered"

    # Парсинг ----------------------------------------------------------

    def test_usage(self) -> None:
        assert self.presenter.usage(locale=self.ru) == "ru:claim-prize-usage"

    def test_invalid_lot_id_includes_raw(self) -> None:
        text = self.presenter.invalid_lot_id(locale=self.ru, raw="abc")
        assert text.startswith("ru:claim-prize-invalid-lot-id")
        assert "raw=abc" in text

    # Prompt + inline-кнопка ------------------------------------------

    def test_prompt_includes_params(self) -> None:
        text = self.presenter.prompt(
            locale=self.ru,
            lot_id=7,
            currency_code="ton_nano",
            amount_native=2_500_000_000,
        )
        assert text.startswith("ru:claim-prize-prompt")
        assert "lot_id=7" in text
        assert "currency=ton_nano" in text
        assert "amount=2500000000" in text

    def test_prompt_keyboard_single_button(self) -> None:
        kb = self.presenter.prompt_keyboard(locale=self.ru, lot_id=42)
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 1
        button = kb.inline_keyboard[0][0]
        assert button.text == "ru:claim-prize-button"
        assert button.callback_data == "claim_prize:42"

    def test_prompt_keyboard_localizes_label(self) -> None:
        kb = self.presenter.prompt_keyboard(locale=self.en, lot_id=42)
        assert kb.inline_keyboard[0][0].text == "en:claim-prize-button"

    # Ошибки -----------------------------------------------------------

    def test_not_found_includes_lot_id(self) -> None:
        text = self.presenter.not_found(locale=self.ru, lot_id=99)
        assert text.startswith("ru:claim-prize-not-found")
        assert "lot_id=99" in text

    def test_already_claimed_includes_lot_id(self) -> None:
        text = self.presenter.already_claimed(locale=self.ru, lot_id=99)
        assert text.startswith("ru:claim-prize-already-claimed")
        assert "lot_id=99" in text

    def test_not_reserved_includes_lot_id_and_status(self) -> None:
        text = self.presenter.not_reserved(
            locale=self.ru,
            lot_id=10,
            status="claimed",
        )
        assert text.startswith("ru:claim-prize-not-reserved")
        assert "lot_id=10" in text
        assert "status=claimed" in text

    def test_wallet_not_linked_includes_currency(self) -> None:
        text = self.presenter.wallet_not_linked(
            locale=self.ru,
            currency_code="usdt_decimal",
        )
        assert text.startswith("ru:claim-prize-wallet-not-linked")
        assert "currency=usdt_decimal" in text

    def test_not_owner_includes_lot_id(self) -> None:
        text = self.presenter.not_owner(locale=self.ru, lot_id=15)
        assert text.startswith("ru:claim-prize-not-owner")
        assert "lot_id=15" in text

    # Финальные исходы ------------------------------------------------

    def test_success_includes_all_params(self) -> None:
        text = self.presenter.success(
            locale=self.ru,
            lot_id=42,
            currency_code="ton_nano",
            amount_native=2_500_000_000,
            actual_fee_native=8_000_000,
            tx_hash="abc123def",
            recipient_address="EQDESTINATION",
        )
        assert text.startswith("ru:claim-prize-success")
        assert "lot_id=42" in text
        assert "currency=ton_nano" in text
        assert "amount=2500000000" in text
        assert "actual_fee=8000000" in text
        assert "tx_hash=abc123def" in text
        assert "address=EQDESTINATION" in text

    def test_refund_includes_all_params(self) -> None:
        text = self.presenter.refund(
            locale=self.en,
            lot_id=42,
            currency_code="usdt_decimal",
            amount_native=5_000_000,
            actual_fee_native=300_000,
            fee_buffer_native=200_000,
        )
        assert text.startswith("en:claim-prize-refund")
        assert "lot_id=42" in text
        assert "currency=usdt_decimal" in text
        assert "amount=5000000" in text
        assert "actual_fee=300000" in text
        assert "fee_buffer=200000" in text

    # Callback-error --------------------------------------------------

    def test_invalid_callback(self) -> None:
        assert self.presenter.invalid_callback(locale=self.ru) == "ru:claim-prize-invalid-callback"

    def test_toast_invalid(self) -> None:
        assert self.presenter.toast_invalid(locale=self.en) == "en:claim-prize-toast-invalid"
