"""Юнит-тесты `RoulettePaidPresenter` и helper-ов сериализации (Спринт 4.1-A).

Покрывает:

* `roulette_paid_callback_data(...)` / `parse_roulette_paid_callback_data(...)` /
  `is_roulette_paid_callback(...)` — round-trip + ошибки;
* `invoice_payload_for(...)` / `parse_invoice_payload(...)` — round-trip;
* презентер: pre-spin карточка с двумя кнопками, gate-warning,
  invoice title/description/label/prices per-pack, result-карточки
  для всех outcome-ов, агрегированная result_pack10, idempotent retry,
  toast-ы.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.monetization import PaidRoulettePack, SpinPaidRouletteResult
from pipirik_wars.bot.presenters.roulette_paid import (
    TG_STARS_CURRENCY,
    RoulettePaidPresenter,
    invoice_payload_for,
    is_roulette_paid_callback,
    parse_invoice_payload,
    parse_roulette_paid_callback_data,
    roulette_paid_callback_data,
)
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    Payment,
    PaymentStatus,
)
from pipirik_wars.domain.roulette import RouletteOutcome, RouletteOutcomeKind
from tests.fakes import FakeMessageBundle


def _bundle() -> IMessageBundle:
    return cast(IMessageBundle, FakeMessageBundle())


def _presenter() -> RoulettePaidPresenter:
    return RoulettePaidPresenter(bundle=_bundle())


# --- Sériализация callback_data ---


class TestCallbackDataSerialization:
    def test_callback_data_round_trip_single(self) -> None:
        data = roulette_paid_callback_data(action="buy_single")
        assert data == "roulette_paid:buy_single"
        parsed = parse_roulette_paid_callback_data(data)
        assert parsed.action == "buy_single"

    def test_callback_data_round_trip_pack_10(self) -> None:
        data = roulette_paid_callback_data(action="buy_pack_10")
        assert data == "roulette_paid:buy_pack_10"
        parsed = parse_roulette_paid_callback_data(data)
        assert parsed.action == "buy_pack_10"

    def test_callback_data_under_telegram_limit(self) -> None:
        # Telegram callback_data hard-cap = 64 байт.
        for action in ("buy_single", "buy_pack_10"):
            data = roulette_paid_callback_data(action=action)
            assert len(data.encode("utf-8")) <= 64

    def test_callback_data_unknown_action_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown roulette_paid callback action"):
            roulette_paid_callback_data(action="buy_pack_99")  # type: ignore[arg-type]

    def test_parse_callback_data_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="must be 'roulette_paid:<action>'"):
            parse_roulette_paid_callback_data("roulette_free:spin")

    def test_parse_callback_data_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown roulette_paid action"):
            parse_roulette_paid_callback_data("roulette_paid:cancel")

    def test_parse_callback_data_too_many_parts(self) -> None:
        with pytest.raises(ValueError, match="must be 'roulette_paid:<action>'"):
            parse_roulette_paid_callback_data("roulette_paid:buy_single:extra")

    def test_is_roulette_paid_callback_true(self) -> None:
        assert is_roulette_paid_callback("roulette_paid:buy_single") is True
        assert is_roulette_paid_callback("roulette_paid:") is True

    def test_is_roulette_paid_callback_false(self) -> None:
        assert is_roulette_paid_callback("roulette_free:spin") is False
        assert is_roulette_paid_callback("boss:show_lobby:1") is False
        assert is_roulette_paid_callback(None) is False


# --- Сериализация invoice_payload ---


class TestInvoicePayloadSerialization:
    def test_invoice_payload_round_trip_single(self) -> None:
        payload = invoice_payload_for(PaidRoulettePack.SINGLE)
        assert payload == "paid_roulette:single"
        assert parse_invoice_payload(payload) is PaidRoulettePack.SINGLE

    def test_invoice_payload_round_trip_pack_10(self) -> None:
        payload = invoice_payload_for(PaidRoulettePack.PACK_10)
        assert payload == "paid_roulette:pack_10"
        assert parse_invoice_payload(payload) is PaidRoulettePack.PACK_10

    def test_invoice_payload_under_telegram_limit(self) -> None:
        # Telegram invoice_payload hard-cap = 128 байт.
        for pack in PaidRoulettePack:
            payload = invoice_payload_for(pack)
            assert len(payload.encode("utf-8")) <= 128

    def test_parse_invoice_payload_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="invoice_payload must be"):
            parse_invoice_payload("free_roulette:single")

    def test_parse_invoice_payload_unknown_pack(self) -> None:
        with pytest.raises(ValueError, match="unknown PaidRoulettePack value"):
            parse_invoice_payload("paid_roulette:pack_99")

    def test_parse_invoice_payload_three_parts_rejected(self) -> None:
        # 3-частьевый payload не подходит ни под v0 (ровно 2), ни
        # под v1 (ровно 4) — отказ.
        with pytest.raises(ValueError, match="invoice_payload must be"):
            parse_invoice_payload("paid_roulette:single:extra")

    # D.8.c: поддержка v1-signed-формата в parse_invoice_payload.

    def test_parse_v1_signed_payload_single(self) -> None:
        # Сигнед-пайлоад `<v>:<pack>:<seed>:<hmac>` — parse берёт parts[1].
        # HMAC НЕ проверяется здесь (это роль verifier-а).
        assert (
            parse_invoice_payload("v1:single:abcdefghij0123456789ABCD:fake-hmac")
            is PaidRoulettePack.SINGLE
        )

    def test_parse_v1_signed_payload_pack_10(self) -> None:
        assert (
            parse_invoice_payload("v1:pack_10:abcdefghij0123456789ABCD:fake-hmac")
            is PaidRoulettePack.PACK_10
        )

    def test_parse_v1_signed_payload_unknown_pack_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown PaidRoulettePack value"):
            parse_invoice_payload("v1:pack_99:abcdefghij0123456789ABCD:fake-hmac")

    def test_parse_v1_signed_payload_wrong_version_prefix_rejected(self) -> None:
        # Первая часть не начинается с 'v' → не v1-format → отказ.
        with pytest.raises(ValueError, match="invoice_payload must be"):
            parse_invoice_payload("x1:single:abcdefghij0123456789ABCD:fake-hmac")


# --- Презентер ---


class TestRoulettePaidPresenterChatVariants:
    def test_group(self) -> None:
        assert _presenter().group(locale=Locale("ru")) == "ru:roulette-paid-group"

    def test_other(self) -> None:
        assert _presenter().other(locale=Locale("en")) == "en:roulette-paid-other"

    def test_not_registered(self) -> None:
        assert _presenter().not_registered(locale=Locale("ru")) == "ru:roulette-paid-not-registered"

    def test_requirement_thickness(self) -> None:
        text = _presenter().requirement_thickness(required=2, actual=1, locale=Locale("ru"))
        assert text == "ru:roulette-paid-requirement-thickness[actual=1,required=2]"


class TestRoulettePaidPresenterPrompt:
    def test_prompt_text(self) -> None:
        text = _presenter().prompt(
            single_cost_stars=1,
            pack10_cost_stars=9,
            pack10_spins=10,
            locale=Locale("ru"),
        )
        assert text.startswith("ru:roulette-paid-prompt[")
        assert "single_cost_stars=1" in text
        assert "pack10_cost_stars=9" in text
        assert "pack10_spins=10" in text

    def test_pack_keyboard_two_buttons(self) -> None:
        kb = _presenter().pack_keyboard(
            single_cost_stars=1,
            pack10_cost_stars=9,
            pack10_spins=10,
            locale=Locale("ru"),
        )
        # Каждая кнопка — на собственной строке (vertical layout).
        assert len(kb.inline_keyboard) == 2
        (single_btn,) = kb.inline_keyboard[0]
        (pack10_btn,) = kb.inline_keyboard[1]
        assert single_btn.callback_data == "roulette_paid:buy_single"
        assert pack10_btn.callback_data == "roulette_paid:buy_pack_10"
        assert "cost_stars=1" in (single_btn.text or "")
        assert "cost_stars=9" in (pack10_btn.text or "")
        assert "pack10_spins=10" in (pack10_btn.text or "")


class TestRoulettePaidPresenterInvoice:
    def test_invoice_title_single(self) -> None:
        assert (
            _presenter().invoice_title(pack=PaidRoulettePack.SINGLE, locale=Locale("ru"))
            == "ru:roulette-paid-invoice-title-single"
        )

    def test_invoice_title_pack_10(self) -> None:
        assert (
            _presenter().invoice_title(pack=PaidRoulettePack.PACK_10, locale=Locale("en"))
            == "en:roulette-paid-invoice-title-pack-10"
        )

    def test_invoice_description_single(self) -> None:
        text = _presenter().invoice_description(
            pack=PaidRoulettePack.SINGLE,
            cost_stars=1,
            pack10_spins=10,
            locale=Locale("ru"),
        )
        assert text == "ru:roulette-paid-invoice-description-single[cost_stars=1]"

    def test_invoice_description_pack_10(self) -> None:
        text = _presenter().invoice_description(
            pack=PaidRoulettePack.PACK_10,
            cost_stars=9,
            pack10_spins=10,
            locale=Locale("ru"),
        )
        assert text.startswith("ru:roulette-paid-invoice-description-pack-10[")
        assert "cost_stars=9" in text
        assert "pack10_spins=10" in text

    def test_invoice_prices_single(self) -> None:
        prices = _presenter().invoice_prices(
            pack=PaidRoulettePack.SINGLE,
            cost_stars=1,
            pack10_spins=10,
            locale=Locale("ru"),
        )
        assert len(prices) == 1
        assert prices[0].label == "ru:roulette-paid-invoice-label-single"
        assert prices[0].amount == 1

    def test_invoice_prices_pack_10(self) -> None:
        prices = _presenter().invoice_prices(
            pack=PaidRoulettePack.PACK_10,
            cost_stars=9,
            pack10_spins=10,
            locale=Locale("en"),
        )
        assert len(prices) == 1
        assert prices[0].label == "en:roulette-paid-invoice-label-pack-10[pack10_spins=10]"
        assert prices[0].amount == 9

    def test_tg_stars_currency_constant(self) -> None:
        assert TG_STARS_CURRENCY == "XTR"


def _payment(*, idempotency_key: str = "paid_roulette:1:tg-charge-001") -> Payment:
    return Payment(
        player_id=1,
        currency=Currency.STARS,
        amount_native=1,
        idempotency_key=IdempotencyKey(idempotency_key),
        status=PaymentStatus.CONFIRMED,
        created_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
        provider_payment_id="tg-charge-001",
        confirmed_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
    )


def _result(
    *,
    pack: PaidRoulettePack,
    outcomes: tuple[RouletteOutcome, ...],
    spent_stars: int,
    idempotent: bool = False,
) -> SpinPaidRouletteResult:
    return SpinPaidRouletteResult(
        outcomes=outcomes,
        spent_stars=spent_stars,
        pack=pack,
        payment=_payment() if not idempotent else None,
        idempotent=idempotent,
    )


class TestRoulettePaidPresenterResultSingle:
    def test_render_result_idempotent(self) -> None:
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(), spent_stars=0, idempotent=True)
        assert (
            _presenter().render_result(result=result, locale=Locale("ru"))
            == "ru:roulette-paid-result-idempotent"
        )

    def test_render_result_single_length(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(outcome,), spent_stars=1)
        text = _presenter().render_result(result=result, locale=Locale("ru"))
        assert text.startswith("ru:roulette-paid-result-single-length[")
        assert "length_cm=42" in text
        assert "spent_stars=1" in text

    def test_render_result_single_item(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.ITEM, length_cm=None)
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(outcome,), spent_stars=1)
        text = _presenter().render_result(result=result, locale=Locale("ru"))
        assert text == "ru:roulette-paid-result-single-item[spent_stars=1]"

    def test_render_result_single_scroll_regular(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_REGULAR, length_cm=None)
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(outcome,), spent_stars=1)
        text = _presenter().render_result(result=result, locale=Locale("ru"))
        assert text == "ru:roulette-paid-result-single-scroll-regular[spent_stars=1]"

    def test_render_result_single_scroll_blessed(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_BLESSED, length_cm=None)
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(outcome,), spent_stars=1)
        text = _presenter().render_result(result=result, locale=Locale("en"))
        assert text == "en:roulette-paid-result-single-scroll-blessed[spent_stars=1]"

    def test_render_result_single_crypto_lot(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.CRYPTO_LOT, lot_id=1)
        result = _result(pack=PaidRoulettePack.SINGLE, outcomes=(outcome,), spent_stars=1)
        text = _presenter().render_result(result=result, locale=Locale("ru"))
        assert text == "ru:roulette-paid-result-single-crypto-lot[spent_stars=1]"


class TestRoulettePaidPresenterResultPack10:
    def test_render_result_pack10_aggregates_correctly(self) -> None:
        # 10 outcomes: 5 LENGTH (по 10/20/30/40/50 см), 2 ITEM, 2 SCROLL_REGULAR,
        # 1 SCROLL_BLESSED. CRYPTO_LOT отсутствует (n_crypto_lot=0).
        outcomes = (
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=10),
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=20),
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=30),
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=40),
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=50),
            RouletteOutcome(kind=RouletteOutcomeKind.ITEM, length_cm=None),
            RouletteOutcome(kind=RouletteOutcomeKind.ITEM, length_cm=None),
            RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_REGULAR, length_cm=None),
            RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_REGULAR, length_cm=None),
            RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_BLESSED, length_cm=None),
        )
        result = _result(pack=PaidRoulettePack.PACK_10, outcomes=outcomes, spent_stars=9)

        text = _presenter().render_result(result=result, locale=Locale("ru"))

        assert text.startswith("ru:roulette-paid-result-pack-10[")
        assert "n_spins=10" in text
        assert "total_length_cm=150" in text  # 10+20+30+40+50
        assert "n_length=5" in text
        assert "n_item=2" in text
        assert "n_scroll_regular=2" in text
        assert "n_scroll_blessed=1" in text
        assert "n_crypto_lot=0" in text
        assert "spent_stars=9" in text


class TestRoulettePaidPresenterToasts:
    def test_toast_thickness_gate(self) -> None:
        text = _presenter().toast_thickness_gate(required=2, actual=1, locale=Locale("ru"))
        assert text == "ru:roulette-paid-toast-thickness-gate[actual=1,required=2]"

    def test_toast_not_registered(self) -> None:
        assert (
            _presenter().toast_not_registered(locale=Locale("ru"))
            == "ru:roulette-paid-toast-not-registered"
        )

    def test_toast_payment_ok(self) -> None:
        assert (
            _presenter().toast_payment_ok(locale=Locale("en"))
            == "en:roulette-paid-toast-payment-ok"
        )

    def test_toast_already_processed(self) -> None:
        assert (
            _presenter().toast_already_processed(locale=Locale("ru"))
            == "ru:roulette-paid-toast-already-processed"
        )

    def test_toast_error(self) -> None:
        assert _presenter().toast_error(locale=Locale("ru")) == "ru:roulette-paid-toast-error"

    def test_payment_invalid_ru(self) -> None:
        # D.8.c: новая карточка отказа для `InvalidStarsPayloadError`.
        assert (
            _presenter().payment_invalid(locale=Locale("ru")) == "ru:roulette-paid-payment-invalid"
        )

    def test_payment_invalid_en(self) -> None:
        assert (
            _presenter().payment_invalid(locale=Locale("en")) == "en:roulette-paid-payment-invalid"
        )
