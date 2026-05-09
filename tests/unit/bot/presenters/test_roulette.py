"""Юнит-тесты `bot/presenters/roulette.py` (Спринт 3.5-D, D.3).

Покрываем:

1. Pure-функции `roulette_callback_data` / `parse_roulette_callback_data` /
   `is_roulette_callback` — серилизация/парсинг `callback_data`,
   инварианты (≤ 64 байт, отказ на unknown action, отказ на bad format).
2. `RoulettePresenter` через **`FakeMessageBundle`** — проверяем, что
   презентер просит правильные ключи и параметры (маркер
   `<locale>:<key>[k=v,...]` детерминистичен и не зависит от
   реальных переводов).
3. `RoulettePresenter` через **`FluentMessageBundle`** (RU + EN) —
   smoke-проверка реальных переводов: вывод содержит ожидаемые
   подстроки и не падает на отсутствующих ключах.
4. `render_result(...)`-диспетчер: SpinResult → текст result-карточки
   для каждого `RouletteOutcomeKind` + idempotent-ветка + invariant
   `idempotent=False && outcome=None` → `ValueError`.
5. Locale-parity для `roulette-free-*`-ключей (RU↔EN). Глобальный
   parity уже покрыт `test_admin_keys_lint.py::TestLocaleParity::test_full_parity`,
   но локальный фокус-тест помогает быстро ловить регрессии.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fluent.syntax import parse as fluent_parse
from fluent.syntax.ast import Message, Term

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.roulette import SpinResult
from pipirik_wars.bot.presenters.roulette import (
    ANIMATION_FRAMES_COUNT,
    RouletteCallbackData,
    RoulettePresenter,
    is_roulette_callback,
    parse_roulette_callback_data,
    roulette_callback_data,
)
from pipirik_wars.domain.roulette import RouletteOutcome, RouletteOutcomeKind
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle

_RU = Locale("ru")
_EN = Locale("en")


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


# ============================================================
# Pure-функции: callback_data
# ============================================================


class TestCallbackData:
    def test_round_trip_spin(self) -> None:
        raw = roulette_callback_data(action="spin")
        parsed = parse_roulette_callback_data(raw)
        assert parsed == RouletteCallbackData(action="spin")

    def test_serialize_format(self) -> None:
        assert roulette_callback_data(action="spin") == "roulette_free:spin"

    def test_serialize_callback_under_64_bytes(self) -> None:
        raw = roulette_callback_data(action="spin")
        assert len(raw.encode()) <= 64

    def test_serialize_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            roulette_callback_data(action="claim")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "roulette_free",
            "roulette_free:spin:extra",
            "x:spin",
            "roulette:spin",
        ],
    )
    def test_parse_rejects_malformed_format(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_roulette_callback_data(raw)

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            parse_roulette_callback_data("roulette_free:eat")


class TestIsRouletteCallback:
    def test_none_returns_false(self) -> None:
        assert is_roulette_callback(None) is False

    def test_other_prefix_returns_false(self) -> None:
        assert is_roulette_callback("boss:join:1") is False
        assert is_roulette_callback("caravan:join:1") is False
        assert is_roulette_callback("enc:confirm:item:scroll") is False
        # `roulette:` без `_free` — не наш префикс (зарезервирован под
        # потенциальные будущие platform-варианты).
        assert is_roulette_callback("roulette:spin") is False

    def test_roulette_free_prefix_returns_true(self) -> None:
        assert is_roulette_callback("roulette_free:spin") is True

    def test_bare_prefix_alone_is_not_callback(self) -> None:
        # `is_roulette_callback("roulette_free")` — без `:` — это не наш формат.
        assert is_roulette_callback("roulette_free") is False


# ============================================================
# RoulettePresenter — FakeMessageBundle (маркеры)
# ============================================================


class TestRoulettePresenterFakeBundle:
    """Маркерные тесты — какие ключи и параметры запрашивает презентер."""

    def test_group_uses_correct_key(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        assert presenter.group(locale=_RU) == "ru:roulette-free-group"

    def test_other_uses_correct_key(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        assert presenter.other(locale=_EN) == "en:roulette-free-other"

    def test_not_registered_uses_correct_key(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        assert presenter.not_registered(locale=_RU) == "ru:roulette-free-not-registered"

    def test_requirement_thickness_passes_required_and_actual(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.requirement_thickness(required=2, actual=1, locale=_EN)
        assert text == "en:roulette-free-requirement-thickness[actual=1,required=2]"

    def test_requirement_length_passes_required_and_actual_cm(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.requirement_length(required_cm=100, actual_cm=42, locale=_RU)
        assert text == "ru:roulette-free-requirement-length[actual_cm=42,required_cm=100]"

    def test_prompt_passes_current_cost_and_remaining(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.prompt(current_length_cm=250, cost_cm=100, locale=_RU)
        assert text == (
            "ru:roulette-free-prompt[cost_cm=100,current_length_cm=250,remaining_cm=150]"
        )

    def test_spin_keyboard_has_single_button_with_spin_callback(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        markup = presenter.spin_keyboard(cost_cm=100, locale=_RU)
        assert len(markup.inline_keyboard) == 1
        assert len(markup.inline_keyboard[0]) == 1
        button = markup.inline_keyboard[0][0]
        assert button.text == "ru:roulette-free-button-spin[cost_cm=100]"
        assert button.callback_data == "roulette_free:spin"

    def test_animation_frame_renders_indexed_key(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        for idx in range(1, ANIMATION_FRAMES_COUNT + 1):
            assert (
                presenter.animation_frame(frame_index=idx, locale=_RU)
                == f"ru:roulette-free-animation-frame-{idx}"
            )

    @pytest.mark.parametrize("bad_idx", [0, -1, ANIMATION_FRAMES_COUNT + 1, 100])
    def test_animation_frame_rejects_out_of_range(self, bad_idx: int) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        with pytest.raises(ValueError):
            presenter.animation_frame(frame_index=bad_idx, locale=_RU)

    def test_result_length_passes_length_and_cost(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.result_length(length_cm=42, cost_cm=100, locale=_RU)
        assert text == "ru:roulette-free-result-length[cost_cm=100,length_cm=42]"

    def test_result_item_passes_cost(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.result_item(cost_cm=100, locale=_EN)
        assert text == "en:roulette-free-result-item[cost_cm=100]"

    def test_result_scroll_regular_passes_cost(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.result_scroll_regular(cost_cm=100, locale=_RU)
        assert text == "ru:roulette-free-result-scroll-regular[cost_cm=100]"

    def test_result_scroll_blessed_passes_cost(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.result_scroll_blessed(cost_cm=100, locale=_EN)
        assert text == "en:roulette-free-result-scroll-blessed[cost_cm=100]"

    def test_result_crypto_lot_passes_cost(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        text = presenter.result_crypto_lot(cost_cm=100, locale=_RU)
        assert text == "ru:roulette-free-result-crypto-lot[cost_cm=100]"

    def test_result_idempotent_uses_correct_key(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        assert presenter.result_idempotent(locale=_RU) == "ru:roulette-free-result-idempotent"

    @pytest.mark.parametrize(
        ("kind_method", "key"),
        [
            ("toast_thickness_gate", "roulette-free-toast-thickness-gate"),
            ("toast_insufficient_length", "roulette-free-toast-insufficient-length"),
            ("toast_not_registered", "roulette-free-toast-not-registered"),
            ("toast_spin_complete", "roulette-free-toast-spin-complete"),
            ("toast_already_processed", "roulette-free-toast-already-processed"),
            ("toast_error", "roulette-free-toast-error"),
        ],
    )
    def test_simple_toasts_route_to_correct_keys(self, kind_method: str, key: str) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        if kind_method == "toast_thickness_gate":
            text = presenter.toast_thickness_gate(required=2, actual=1, locale=_RU)
            assert text == f"ru:{key}[actual=1,required=2]"
        elif kind_method == "toast_insufficient_length":
            text = presenter.toast_insufficient_length(required_cm=100, actual_cm=50, locale=_RU)
            assert text == f"ru:{key}[actual_cm=50,required_cm=100]"
        else:
            method = getattr(presenter, kind_method)
            assert method(locale=_RU) == f"ru:{key}"

    # --- render_result диспетчер ---

    def test_render_result_idempotent_returns_idempotent_text(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        result = SpinResult(outcome=None, spent_cm=0, idempotent=True)
        assert presenter.render_result(result=result, cost_cm=100, locale=_RU) == (
            "ru:roulette-free-result-idempotent"
        )

    def test_render_result_length_dispatches_to_length(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=37)
        result = SpinResult(outcome=outcome, spent_cm=100, idempotent=False)
        text = presenter.render_result(result=result, cost_cm=100, locale=_RU)
        assert text == "ru:roulette-free-result-length[cost_cm=100,length_cm=37]"

    @pytest.mark.parametrize(
        ("kind", "key_suffix"),
        [
            (RouletteOutcomeKind.ITEM, "item"),
            (RouletteOutcomeKind.SCROLL_REGULAR, "scroll-regular"),
            (RouletteOutcomeKind.SCROLL_BLESSED, "scroll-blessed"),
            (RouletteOutcomeKind.CRYPTO_LOT, "crypto-lot"),
        ],
    )
    def test_render_result_non_length_dispatches_per_kind(
        self, kind: RouletteOutcomeKind, key_suffix: str
    ) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        outcome = RouletteOutcome(kind=kind)
        result = SpinResult(outcome=outcome, spent_cm=100, idempotent=False)
        text = presenter.render_result(result=result, cost_cm=100, locale=_RU)
        assert text == f"ru:roulette-free-result-{key_suffix}[cost_cm=100]"

    def test_render_result_invariant_violation_raises(self) -> None:
        presenter = RoulettePresenter(bundle=FakeMessageBundle())
        # Невалидный SpinResult: idempotent=False, но outcome=None.
        result = SpinResult(outcome=None, spent_cm=100, idempotent=False)
        with pytest.raises(ValueError, match="invariant violated"):
            presenter.render_result(result=result, cost_cm=100, locale=_RU)


# ============================================================
# RoulettePresenter — FluentMessageBundle (smoke-проверка переводов)
# ============================================================


class TestRoulettePresenterFluent:
    """Smoke-проверки реальных переводов RU + EN."""

    def test_not_registered_ru_smoke(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.not_registered(locale=_RU)
        # Ключ существует и содержит /start (как у `enchant-not-registered`).
        assert "/start" in text or "регистр" in text.lower()

    def test_not_registered_en_smoke(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.not_registered(locale=_EN)
        assert "/start" in text or "regist" in text.lower()

    def test_prompt_renders_numbers_in_ru(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.prompt(current_length_cm=250, cost_cm=100, locale=_RU)
        assert "250" in text
        assert "100" in text

    def test_prompt_renders_numbers_in_en(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.prompt(current_length_cm=250, cost_cm=100, locale=_EN)
        assert "250" in text
        assert "100" in text

    def test_requirement_thickness_renders_numbers_in_ru(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.requirement_thickness(required=2, actual=1, locale=_RU)
        assert "2" in text
        assert "1" in text

    def test_requirement_length_renders_cm_in_en(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.requirement_length(required_cm=100, actual_cm=42, locale=_EN)
        assert "100" in text
        assert "42" in text

    def test_spin_keyboard_uses_localized_label(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        markup_ru = presenter.spin_keyboard(cost_cm=100, locale=_RU)
        markup_en = presenter.spin_keyboard(cost_cm=100, locale=_EN)
        assert markup_ru.inline_keyboard[0][0].callback_data == "roulette_free:spin"
        assert markup_en.inline_keyboard[0][0].callback_data == "roulette_free:spin"
        # Подписи разные в RU/EN, но обе содержат "100".
        assert "100" in markup_ru.inline_keyboard[0][0].text
        assert "100" in markup_en.inline_keyboard[0][0].text
        assert markup_ru.inline_keyboard[0][0].text != markup_en.inline_keyboard[0][0].text

    def test_animation_frames_render_in_ru(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        for idx in range(1, ANIMATION_FRAMES_COUNT + 1):
            text = presenter.animation_frame(frame_index=idx, locale=_RU)
            assert text  # не пусто

    def test_result_length_renders_numbers_in_ru(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        text = presenter.result_length(length_cm=42, cost_cm=100, locale=_RU)
        assert "42" in text

    def test_toast_already_processed_renders_in_both_locales(self) -> None:
        presenter = RoulettePresenter(bundle=_fluent_bundle())
        ru = presenter.toast_already_processed(locale=_RU)
        en = presenter.toast_already_processed(locale=_EN)
        assert ru
        assert en
        assert ru != en


# ============================================================
# Locale parity: roulette-free-* keys
# ============================================================


def _roulette_keys(ftl_path: Path) -> set[str]:
    resource = fluent_parse(ftl_path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for entry in resource.body:
        if isinstance(entry, Message | Term) and entry.id.name.startswith("roulette-free-"):
            keys.add(entry.id.name)
    return keys


class TestRouletteLocaleParity:
    def test_full_parity(self) -> None:
        locales_dir = Path(__file__).resolve().parents[4] / "locales"
        ru_keys = _roulette_keys(locales_dir / "ru.ftl")
        en_keys = _roulette_keys(locales_dir / "en.ftl")
        only_ru = sorted(ru_keys - en_keys)
        only_en = sorted(en_keys - ru_keys)
        assert only_ru == [], f"roulette-free-* ключи только в ru.ftl: {only_ru}"
        assert only_en == [], f"roulette-free-* ключи только в en.ftl: {only_en}"

    def test_minimum_count_sanity(self) -> None:
        locales_dir = Path(__file__).resolve().parents[4] / "locales"
        ru_keys = _roulette_keys(locales_dir / "ru.ftl")
        # На D.2 минимум: group, other, not-registered, requirement-thickness/length,
        # prompt, button-spin, 3 frames, 5 result-* + idempotent, 6 toast-* — итого 21+.
        assert len(ru_keys) >= 20, (
            f"ожидалось ≥ 20 roulette-free-* ключей, получено {len(ru_keys)}: {sorted(ru_keys)}"
        )
