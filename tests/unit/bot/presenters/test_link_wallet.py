"""Юнит-тесты `LinkWalletPresenter` + callback-сериализаторов (Спринт 4.1-D.6).

`LinkWalletPresenter` — тонкий слой над `IMessageBundle`, поэтому
тестируем именно склейку ключей и параметров (через
`FakeMessageBundle`-маркеры) и контракт callback-сериализатора.
"""

from __future__ import annotations

from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.link_wallet import (
    LinkWalletPresenter,
    link_wallet_callback_data,
    parse_link_wallet_callback_data,
)
from pipirik_wars.domain.monetization.value_objects import Currency
from tests.fakes import FakeMessageBundle

# ────────────────────────── callback_data ─────────────────────────


class TestLinkWalletCallbackData:
    def test_ton_serializes(self) -> None:
        assert link_wallet_callback_data("ton") == "link_wallet:select:ton"

    def test_usdt_serializes(self) -> None:
        assert link_wallet_callback_data("usdt") == "link_wallet:select:usdt"

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown link_wallet currency key"):
            link_wallet_callback_data("doge")  # type: ignore[arg-type]

    def test_parse_round_trip_ton(self) -> None:
        parsed = parse_link_wallet_callback_data("link_wallet:select:ton")
        assert parsed.action == "select"
        assert parsed.currency_key == "ton"
        assert parsed.to_currency() == Currency.TON_NANO

    def test_parse_round_trip_usdt(self) -> None:
        parsed = parse_link_wallet_callback_data("link_wallet:select:usdt")
        assert parsed.action == "select"
        assert parsed.currency_key == "usdt"
        assert parsed.to_currency() == Currency.USDT_DECIMAL

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "link_wallet",
            "link_wallet:select",
            "link_wallet:select:foo",
            "link_wallet:cancel:ton",
            "other:select:ton",
            "link_wallet:select:ton:extra",
        ],
    )
    def test_parse_invalid_raises(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_link_wallet_callback_data(raw)


# ────────────────────────── presenter ─────────────────────────────


class TestLinkWalletPresenter:
    def setup_method(self) -> None:
        self.bundle = cast(IMessageBundle, FakeMessageBundle())
        self.presenter = LinkWalletPresenter(bundle=self.bundle)
        self.ru = Locale("ru")
        self.en = Locale("en")

    # /link_wallet -----------------------------------------------------

    def test_group(self) -> None:
        assert self.presenter.group(locale=self.ru) == "ru:link-wallet-group"

    def test_other(self) -> None:
        assert self.presenter.other(locale=self.en) == "en:link-wallet-other"

    def test_not_registered(self) -> None:
        assert self.presenter.not_registered(locale=self.ru) == "ru:link-wallet-not-registered"

    def test_prompt(self) -> None:
        assert self.presenter.prompt(locale=self.ru) == "ru:link-wallet-prompt"

    def test_prompt_keyboard_two_rows_with_localized_labels(self) -> None:
        kb = self.presenter.prompt_keyboard(locale=self.ru)
        assert len(kb.inline_keyboard) == 2
        assert kb.inline_keyboard[0][0].text == "ru:link-wallet-button-ton"
        assert kb.inline_keyboard[0][0].callback_data == "link_wallet:select:ton"
        assert kb.inline_keyboard[1][0].text == "ru:link-wallet-button-usdt"
        assert kb.inline_keyboard[1][0].callback_data == "link_wallet:select:usdt"

    def test_instructions_ton(self) -> None:
        assert (
            self.presenter.instructions(currency_key="ton", locale=self.ru)
            == "ru:link-wallet-instructions-ton"
        )

    def test_instructions_usdt(self) -> None:
        assert (
            self.presenter.instructions(currency_key="usdt", locale=self.en)
            == "en:link-wallet-instructions-usdt"
        )

    def test_toast_invalid(self) -> None:
        assert self.presenter.toast_invalid(locale=self.ru) == "ru:link-wallet-toast-invalid"

    # /link_wallet_confirm --------------------------------------------

    def test_confirm_group(self) -> None:
        assert self.presenter.confirm_group(locale=self.ru) == "ru:link-wallet-confirm-group"

    def test_confirm_other(self) -> None:
        assert self.presenter.confirm_other(locale=self.ru) == "ru:link-wallet-confirm-other"

    def test_confirm_usage(self) -> None:
        assert self.presenter.confirm_usage(locale=self.ru) == "ru:link-wallet-confirm-usage"

    def test_confirm_unsupported_includes_code(self) -> None:
        text = self.presenter.confirm_unsupported_currency(
            locale=self.ru,
            code="doge",
        )
        assert text.startswith("ru:link-wallet-confirm-unsupported")
        assert "code=doge" in text

    def test_confirm_invalid_proof(self) -> None:
        assert (
            self.presenter.confirm_invalid_proof(locale=self.ru)
            == "ru:link-wallet-confirm-invalid-proof"
        )

    def test_confirm_linked_includes_params(self) -> None:
        text = self.presenter.confirm_linked(
            locale=self.ru,
            address="EQADDR",
            currency_code="ton_nano",
        )
        assert text.startswith("ru:link-wallet-confirm-linked")
        assert "address=EQADDR" in text
        assert "currency=ton_nano" in text

    def test_confirm_relinked_includes_params(self) -> None:
        text = self.presenter.confirm_relinked(
            locale=self.en,
            address="EQNEW",
            currency_code="usdt_decimal",
        )
        assert text.startswith("en:link-wallet-confirm-relinked")
        assert "address=EQNEW" in text
        assert "currency=usdt_decimal" in text

    def test_confirm_already_linked_includes_params(self) -> None:
        text = self.presenter.confirm_already_linked(
            locale=self.ru,
            address="EQOLD",
            currency_code="ton_nano",
        )
        assert text.startswith("ru:link-wallet-confirm-already-linked")
        assert "address=EQOLD" in text
        assert "currency=ton_nano" in text
